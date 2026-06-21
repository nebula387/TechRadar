import json
import logging
import re
from app.models import RawItem, ScoredItem, Category
from app.llm.client import groq_complete

logger = logging.getLogger(__name__)

CATEGORIES = "Developer Tool, AI Model, Research Paper, Open Source, AI Agent, MCP Server, Dataset"

BATCH_SYSTEM = """You are an expert tech curator with extremely high standards.
Evaluate a list of tech items for publishing to senior developers and ML engineers.
Be VERY strict. Reject anything that is:
- Generic or "another X tool" without genuine novelty
- Tutorial or beginner content
- Already well-known without a major recent update
- Lacks concrete practical value
- Pure marketing / startup announcement

Only approve items that are genuinely novel, solve a real pain point elegantly,
have significant community traction, and are relevant to AI, ML, or developer productivity.
Minimum score to approve: 85."""

BATCH_PROMPT = """Evaluate each item below. Return ONLY a valid JSON array, one object per item, same order.

Items:
{items_block}

Required JSON array format:
[
  {{
    "index": 1,
    "approve": true,
    "score": 87,
    "novelty": 8,
    "practical_value": 9,
    "wow_factor": 7,
    "category": "Developer Tool",
    "audience": "ML Engineers",
    "reason": "one sentence",
    "emoji": "🚀",
    "accent_color": "#6366f1"
  }},
  ...
]

category must be one of: {categories}
If score < 85, set approve: false.
Return ONLY the JSON array, no explanation."""


def _format_items_block(items: list[RawItem]) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            f"[{i}] {item.title} | Stars: {item.stars or 'N/A'} | Source: {item.source.value}\n"
            f"    Description: {item.description[:200]}"
        )
    return "\n\n".join(lines)


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _build_scored_item(item: RawItem, data: dict) -> ScoredItem | None:
    if not data.get("approve", False):
        logger.info(f"LLM rejected: '{item.title[:60]}' — {data.get('reason', '')}")
        return None
    score = int(data.get("score", 0))
    if score < 85:
        logger.info(f"LLM low score ({score}): '{item.title[:60]}'")
        return None
    try:
        category = Category(data.get("category", "Developer Tool"))
    except ValueError:
        category = Category.DEVELOPER_TOOL

    logger.info(f"LLM approved: '{item.title[:60]}' score={score}")
    return ScoredItem(
        **item.model_dump(),
        score=score,
        category=category,
        audience=data.get("audience", "Developers"),
        is_interesting=True,
        novelty=int(data.get("novelty", 5)),
        practical_value=int(data.get("practical_value", 5)),
        wow_factor=int(data.get("wow_factor", 5)),
        reason=data.get("reason", ""),
        emoji=data.get("emoji", "🔧"),
        accent_color=data.get("accent_color", "#6366f1"),
    )


async def judge_items(items: list[RawItem]) -> list[ScoredItem]:
    """Evaluate all items in a single Groq call (batch mode) to save API quota."""
    if not items:
        return []

    # Groq context window limits: split into chunks of 15 to be safe
    chunk_size = 15
    approved: list[ScoredItem] = []

    for chunk_start in range(0, len(items), chunk_size):
        chunk = items[chunk_start: chunk_start + chunk_size]
        approved.extend(await _judge_chunk(chunk, offset=chunk_start))

    logger.info(f"LLM judge: {len(approved)} approved / {len(items)} evaluated")
    return approved


async def _judge_chunk(items: list[RawItem], offset: int = 0) -> list[ScoredItem]:
    prompt = BATCH_PROMPT.format(
        items_block=_format_items_block(items),
        categories=CATEGORIES,
    )
    try:
        response = await groq_complete(prompt, system=BATCH_SYSTEM, max_tokens=2048)
        results = _extract_json_array(response)

        approved = []
        for entry in results:
            idx = int(entry.get("index", 0)) - 1  # convert to 0-based
            if idx < 0 or idx >= len(items):
                continue
            item = items[idx]
            scored = _build_scored_item(item, entry)
            if scored:
                approved.append(scored)
        return approved

    except json.JSONDecodeError as e:
        logger.error(f"LLM batch response JSON parse error: {e}")
        logger.debug(f"Raw response: {response[:500]}")
        return []
    except Exception as e:
        logger.error(f"LLM batch judge failed: {e}")
        return []


async def judge_item(item: RawItem) -> ScoredItem | None:
    """Single-item judge (used when only one item needs evaluation)."""
    results = await _judge_chunk([item])
    return results[0] if results else None
