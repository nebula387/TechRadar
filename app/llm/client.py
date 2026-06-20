import httpx
import asyncio
import logging
import time
from app.config import get_settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def _post_with_retry(url: str, headers: dict, payload: dict, max_retries: int = 3) -> dict:
    delay = 2.0
    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, headers=headers, json=payload)
                latency = time.monotonic() - t0

                if resp.status_code == 429:
                    wait = delay * (2 ** attempt)
                    logger.warning(f"Rate limited, retrying in {wait:.1f}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                    continue

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
            await asyncio.sleep(delay * (2 ** attempt))

    raise RuntimeError(f"LLM call failed after {max_retries} attempts")


def _messages(prompt: str, system: str) -> list[dict]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


async def groq_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    s = get_settings()
    if not s.groq_api_key:
        raise ValueError("GROQ_API_KEY not set")
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
    s = get_settings()
    if not s.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
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
