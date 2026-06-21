import httpx
import asyncio
import logging
import time
from app.config import get_settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


async def _post_with_retry(url: str, headers: dict, payload: dict, max_retries: int = 4) -> dict:
    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, headers=headers, json=payload)
                latency = time.monotonic() - t0

                if resp.status_code == 429:
                    retry_after = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-requests")
                    backoff = 30.0 * (2 ** attempt)  # 30s, 60s, 120s, 240s
                    if retry_after:
                        try:
                            wait = min(float(retry_after), 120.0)
                        except ValueError:
                            wait = backoff
                    else:
                        wait = backoff
                    logger.warning(f"Rate limited (429), waiting {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue

                if 400 <= resp.status_code < 500:
                    # Client errors (404 bad model, 401 bad key, 400 bad request) won't fix
                    # themselves on retry — fail fast instead of waiting 35 seconds
                    logger.error(f"Client error {resp.status_code}: {resp.text[:200]}")
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:100]}")

                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                logger.info(
                    "LLM call: model=%s latency=%.2fs in=%s out=%s",
                    payload.get("model"),
                    latency,
                    usage.get("prompt_tokens", "?"),
                    usage.get("completion_tokens", "?"),
                )
                return data
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %s on attempt %d: %s", e.response.status_code, attempt + 1, e)
        except Exception as e:
            logger.error("LLM call error on attempt %d: %s", attempt + 1, e)

        if attempt < max_retries - 1:
            await asyncio.sleep(5.0 * (2 ** attempt))

    raise RuntimeError(f"LLM call failed after {max_retries} attempts")


def _messages(prompt: str, system: str) -> list[dict]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


async def nvidia_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """NVIDIA NIM API — primary LLM provider for filtering."""
    s = get_settings()
    if not s.nvidia_api_key:
        raise ValueError("NVIDIA_API_KEY not set")
    data = await _post_with_retry(
        NVIDIA_URL,
        headers={"Authorization": f"Bearer {s.nvidia_api_key}", "Content-Type": "application/json"},
        payload={
            "model": s.nvidia_model,
            "messages": _messages(prompt, system),
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
    )
    return data["choices"][0]["message"]["content"]


async def groq_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """Call NVIDIA NIM (primary); fall back to Groq if NVIDIA fails."""
    s = get_settings()
    if s.nvidia_api_key:
        try:
            return await nvidia_complete(prompt, system=system, max_tokens=max_tokens)
        except RuntimeError as e:
            logger.warning(f"NVIDIA failed ({e}), falling back to Groq")
    if not s.groq_api_key:
        raise ValueError("Neither NVIDIA_API_KEY nor GROQ_API_KEY is set")
    data = await _post_with_retry(
        GROQ_URL,
        headers={"Authorization": f"Bearer {s.groq_api_key}", "Content-Type": "application/json"},
        payload={
            "model": s.groq_model,
            "messages": _messages(prompt, system),
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
    )
    return data["choices"][0]["message"]["content"]


async def openrouter_complete(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """Content generation: OpenRouter first, NVIDIA as fallback."""
    s = get_settings()
    if s.openrouter_api_key:
        try:
            data = await _post_with_retry(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {s.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": s.website_base_url,
                    "X-Title": "TechRadar AI",
                },
                payload={
                    "model": s.openrouter_model,
                    "messages": _messages(prompt, system),
                    "temperature": 0.7,
                    "max_tokens": max_tokens,
                },
            )
            return data["choices"][0]["message"]["content"]
        except RuntimeError as e:
            logger.warning(f"OpenRouter failed ({e}), falling back to NVIDIA")

    # Fallback: NVIDIA NIM (also good at generation, creative tasks)
    return await nvidia_complete(prompt, system=system, max_tokens=max_tokens)
