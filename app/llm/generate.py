import json
import logging
import re
import asyncio
from datetime import datetime
from app.models import ScoredItem, GeneratedContent
from app.llm.client import openrouter_complete

logger = logging.getLogger(__name__)


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_/]+", "-", s).strip("-")
    prefix = datetime.utcnow().strftime("%Y%m%d")
    return f"{prefix}-{s[:60]}"


async def _telegram(item: ScoredItem) -> str:
    prompt = f"""Ты редактор популярного русскоязычного Telegram-канала об ИИ и инструментах разработчика.
Напиши пост на РУССКОМ языке:
- Разговорный, живой стиль (не корпоративный)
- 3–5 предложений максимум
- Начни с эмодзи: {item.emoji}
- Жирный заголовок в первой строке (**заголовок**)
- Объясни ЧТО это и ПОЧЕМУ это важно ПРЯМО СЕЙЧАС
- Заверши ссылкой: {item.url}

Данные:
Название: {item.title}
Описание: {item.description[:400]}
Категория: {item.category.value}
Почему публикуем: {item.reason}"""

    return await openrouter_complete(prompt, max_tokens=400)


async def _instagram(item: ScoredItem) -> tuple[str, list[str]]:
    prompt = f"""Write an Instagram caption for this tech discovery.

Title: {item.title}
Description: {item.description[:300]}
Why it matters: {item.reason}
Category: {item.category.value}

Rules:
- 2–3 sentences, conversational, highlight what's exciting
- End with "Link in bio 🔗"
- Return ONLY valid JSON (no markdown):
{{"caption": "...", "hashtags": ["tag1", "tag2", ...]}}
- Include 8–10 relevant hashtags (no # symbol, just words)"""

    try:
        response = await openrouter_complete(prompt, max_tokens=350)
        m = re.search(r"\{.*\}", response, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return data.get("caption", ""), data.get("hashtags", [])
    except Exception as e:
        logger.error(f"Instagram generation failed: {e}")
    # Fallback
    return (
        f"{item.emoji} {item.title}\n\n{item.description[:150]}\n\nLink in bio 🔗",
        ["tech", "ai", "developer", "machinelearning", "opensource"],
    )


async def _website(item: ScoredItem) -> tuple[str, str]:
    prompt = f"""Write a short tech article (300–400 words) for a senior-developer blog.

Topic: {item.title}
Description: {item.description[:400]}
Why it matters: {item.reason}
Category: {item.category.value}
Audience: {item.audience}

Structure:
1. SEO headline under 70 chars — first line, no prefix or label
2. Lead paragraph (what it is, why it matters now)
3. Key features / what makes it unique (2–3 paragraphs)
4. Who should care and practical use cases
5. Closing thought

Tone: expert, clear, zero fluff. Start with the headline on the very first line."""

    response = await openrouter_complete(prompt, max_tokens=700)
    lines = response.strip().split("\n")
    title = lines[0].lstrip("#").strip()
    body = "\n".join(lines[1:]).strip()
    return title, body


async def generate_content(item: ScoredItem) -> GeneratedContent | None:
    try:
        telegram_text, (ig_caption, ig_hashtags), (web_title, web_body) = await asyncio.gather(
            _telegram(item),
            _instagram(item),
            _website(item),
        )

        return GeneratedContent(
            item=item,
            telegram_text_ru=telegram_text,
            instagram_caption_en=ig_caption,
            instagram_hashtags=ig_hashtags,
            twitter_thread_en=[],     # enabled later
            linkedin_post_en="",      # enabled later
            reddit_title_en=item.title,
            reddit_body_en=item.description,
            website_title_en=web_title,
            website_body_en=web_body,
            website_slug=_slug(item.title),
            tags=item.tags[:5],
        )
    except Exception as e:
        logger.error(f"Content generation failed for '{item.title[:60]}': {e}")
        return None
