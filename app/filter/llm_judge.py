import json
import logging
import re
from app.models import RawItem, ScoredItem, Category
from app.llm.client import groq_complete

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """You are an expert tech curator with extremely high standards.
Decide if the following item is worth publishing to senior developers and ML engineers.
Be VERY strict. Reject anything that is:
- Generic or "another X tool" without genuine novelty
- Tutorial or beginner content
- Already well-known without a major recent update
- Lacks concrete practical value
- Pure marketing / startup announcement without substance

Only approve items that are:
✅ Genuinely novel or a meaningful breakthrough
✅ Solves a real pain point in an elegant way
✅ Would make an expert say "wow, I didn't know this existed"
✅ Has significant community traction
✅ Relevant to AI, ML, or developer productivity"""

JUDGE_PROMPT = """Item:
Title: {title}
Description: {description}
Stars/Score: {metric}
Source: {source}

Respond with ONLY valid JSON (no markdown fences):
{{
  "approve": true,
  "score": 87,
  "novelty": 8,
  "practical_value": 9,
  "wow_factor": 8,
  "category": "Developer Tool",
  "audience": "ML Engineers",
  "reason": "one sentence why",
  "emoji": "🚀",
  "accent_color": "#6366f1"
}}

Minimum score to approve: 85. If score < 85, set approve: false.
category must be one of: Developer Tool, AI Model, Research Paper, Open Source, AI Agent, MCP Server, Dataset"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


async def judge_item(item: RawItem) -> ScoredItem | None:
    prompt = JUDGE_PROMPT.format(
        title=item.title,
        description=item.description[:500],
        metric=item.stars or "N/A",
        source=item.source.value,
    )
    try:
        response = await groq_complete(prompt, system=JUDGE_SYSTEM)
        data = _extract_json(response)

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

        scored = ScoredItem(
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
        logger.info(f"LLM approved: '{item.title[:60]}' score={score}")
        return scored
    except Exception as e:
        logger.error(f"LLM judge failed for '{item.title[:60]}': {e}")
        return None


async def judge_items(items: list[RawItem]) -> list[ScoredItem]:
    approved = []
    for item in items:
        result = await judge_item(item)
        if result:
            approved.append(result)
    logger.info(f"LLM judge: {len(approved)} approved / {len(items)} evaluated")
    return approved
