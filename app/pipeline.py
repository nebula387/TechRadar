import logging
from datetime import datetime
from pathlib import Path
from app.models import PublishedRecord
from app.collectors.base import BaseCollector
from app.filter.quality_gate import filter_items
from app.filter.llm_judge import judge_items
from app.llm.generate import generate_content
from app.image.card import generate_card
from app.publishers.telegram import TelegramPublisher
from app.publishers.instagram import InstagramPublisher
from app.publishers.website import WebsitePublisher
from app.database.storage import Storage
from app.config import get_settings

logger = logging.getLogger(__name__)


async def _publish_to_all(content, storage: Storage) -> list[str]:
    publishers = [
        TelegramPublisher(),
        InstagramPublisher(),
        WebsitePublisher(),
    ]
    published_channels: list[str] = []
    results: dict = {}

    for pub in publishers:
        if not pub.is_enabled:
            continue
        try:
            result = await pub.publish(content)
            published_channels.append(pub.channel_name)
            results[pub.channel_name] = result
            logger.info(f"Published to {pub.channel_name}")
        except Exception as e:
            logger.error(f"Publisher '{pub.channel_name}' failed: {e}")

    if published_channels:
        record = PublishedRecord(
            item_url=content.item.url,
            source=content.item.source,
            score=content.item.score,
            published_at=datetime.utcnow(),
            channels=published_channels,
            telegram_message_id=results.get("telegram", {}).get("message_id"),
            instagram_post_id=results.get("instagram", {}).get("post_id"),
        )
        storage.save_published(record)

    return published_channels


async def run_pipeline(collectors: list[BaseCollector]) -> None:
    s = get_settings()
    storage = Storage(s.database_url)

    today_count = storage.get_today_count()
    if today_count >= s.max_posts_per_day:
        logger.info(f"Daily limit reached ({today_count}/{s.max_posts_per_day}), skipping pipeline")
        return

    # ── Collect ──────────────────────────────────────────────────────────────
    all_items = []
    for collector in collectors:
        try:
            items = await collector.collect()
            all_items.extend(items)
        except Exception as e:
            logger.error(f"Collector '{collector.source_name}' failed: {e}")

    if not all_items:
        logger.info("No items collected")
        return

    logger.info(f"Total collected: {len(all_items)} items")

    # ── Stage 1: Hard pre-filter ─────────────────────────────────────────────
    filtered = filter_items(all_items, storage)
    if not filtered:
        logger.info("All items rejected by quality gate")
        return

    # ── Stage 2: LLM judge ───────────────────────────────────────────────────
    scored = await judge_items(filtered)
    if not scored:
        logger.info("All items rejected by LLM judge")
        return

    # Best items first
    scored.sort(key=lambda x: x.score, reverse=True)

    # ── Generate + Publish (or save for approval) ────────────────────────────
    processed = 0
    images_dir = Path("./data/images")
    images_dir.mkdir(parents=True, exist_ok=True)

    for item in scored:
        remaining = s.max_posts_per_day - (today_count + processed)
        if remaining <= 0:
            break

        content = await generate_content(item)
        if not content:
            continue

        # Image card
        card_path = images_dir / f"{content.website_slug}.png"
        generated = generate_card(
            title=item.title,
            description=item.description[:120],
            category=item.category.value,
            emoji=item.emoji,
            accent_color=item.accent_color,
            source=item.source.value,
            score=item.score,
            output_path=card_path,
        )
        if generated:
            content.image_path = str(generated)

        if s.enable_approval_mode:
            # Save to DB and send preview to admin — do not publish yet
            from app.bot import send_preview
            storage.save_pending(
                slug=content.website_slug,
                item_url=item.url,
                content_json=content.model_dump_json(),
                image_path=content.image_path,
            )
            await send_preview(content, storage)
            logger.info(f"⏳ Pending approval: '{item.title[:60]}'")
            processed += 1

            # After sending all previews, start approval polling loop
            if processed >= len(scored) or processed >= remaining:
                from app.bot import poll_loop
                timeout = s.approval_timeout_seconds
                logger.info(f"Starting approval loop (timeout={timeout}s)...")
                await poll_loop(timeout_seconds=timeout)
        else:
            channels = await _publish_to_all(content, storage)
            if channels:
                processed += 1
                logger.info(f"✅ Published '{item.title[:60]}' → {channels}")

    mode = "pending approval" if s.enable_approval_mode else "published"
    logger.info(f"Pipeline done: {processed} item(s) {mode} this run")
