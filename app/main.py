import asyncio
import logging
import sys
import argparse
from pathlib import Path

Path("./data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("./data/techradar.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

COLLECTOR_MAP = {
    "github": "app.collectors.github.GitHubCollector",
    "github_trending": "app.collectors.github_trending.GitHubTrendingCollector",
    "hackernews": "app.collectors.hackernews.HackerNewsCollector",
    "huggingface": "app.collectors.huggingface.HuggingFaceCollector",
    "arxiv": "app.collectors.arxiv.ArxivCollector",
    "producthunt": "app.collectors.producthunt.ProductHuntCollector",
}


def _load_collector(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)()


def _check_config() -> list[str]:
    """Return list of warnings about missing config."""
    from app.config import get_settings
    s = get_settings()
    warnings = []
    if not s.groq_api_key:
        warnings.append("❌ GROQ_API_KEY not set — LLM judge will fail")
    if not s.openrouter_api_key:
        warnings.append("❌ OPENROUTER_API_KEY not set — content generation will fail")
    if not s.telegram_bot_token:
        warnings.append("❌ TELEGRAM_BOT_TOKEN not set — Telegram publish will fail")
    if not s.telegram_channel_id and s.enable_telegram:
        warnings.append("❌ TELEGRAM_CHANNEL_ID not set")
    if not s.telegram_admin_chat_id:
        warnings.append("⚠️  TELEGRAM_ADMIN_CHAT_ID not set — admin previews disabled")
    if not s.github_token:
        warnings.append("⚠️  GITHUB_TOKEN not set — GitHub API limited to 60 req/hr")
    return warnings


async def run_dry_run(collectors) -> None:
    """
    Collect → filter → LLM judge → generate content for top 5 → send to admin bot.
    Nothing is published to the channel. Used to verify the pipeline works.
    """
    import json
    from app.config import get_settings
    from app.database.storage import Storage
    from app.filter.quality_gate import filter_items, passes_quality_gate
    from app.filter.llm_judge import judge_items
    from app.llm.generate import generate_content
    from app.image.card import generate_card
    from app.bot import send_preview, _tg_post

    s = get_settings()
    storage = Storage(s.database_url)
    admin_chat = s.telegram_admin_chat_id

    def log_and_send(text: str):
        logger.info(text.replace("*", "").replace("`", ""))
        return text

    lines = ["🔍 *TechRadar DRY RUN*\n"]

    # ── 1. Config check ──────────────────────────────────────────────────────
    warnings = _check_config()
    if warnings:
        lines.append("*⚙️ Config warnings:*")
        lines.extend(warnings)
        lines.append("")

    # ── 2. Collect ───────────────────────────────────────────────────────────
    lines.append("*📡 Collecting...*")
    all_items = []
    for collector in collectors:
        try:
            items = await collector.collect()
            lines.append(f"  • {collector.source_name}: {len(items)} items")
            all_items.extend(items)
        except Exception as e:
            lines.append(f"  • {collector.source_name}: ❌ {e}")
    lines.append(f"  *Total: {len(all_items)} items*\n")

    if not all_items:
        lines.append("❌ No items collected — check API keys and network")
        await _send_to_admin(admin_chat, s.telegram_bot_token, "\n".join(lines))
        return

    # ── 3. Quality gate ──────────────────────────────────────────────────────
    rejection_reasons: dict[str, int] = {}
    passed_items = []
    for item in all_items:
        if storage.is_published(item.url):
            rejection_reasons["already published"] = rejection_reasons.get("already published", 0) + 1
            continue
        ok, reason = passes_quality_gate(item, storage)
        if ok:
            passed_items.append(item)
        else:
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    lines.append("*🚫 Quality Gate:*")
    lines.append(f"  Passed: {len(passed_items)} / {len(all_items)}")
    for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1])[:6]:
        lines.append(f"  ✗ {reason}: {count}")
    lines.append("")

    if not passed_items:
        lines.append("❌ All items rejected by quality gate")
        await _send_to_admin(admin_chat, s.telegram_bot_token, "\n".join(lines))
        return

    # ── 4. LLM judge (top 10 by stars to save quota) ────────────────────────
    candidates = sorted(passed_items, key=lambda i: i.stars or 0, reverse=True)[:10]
    lines.append(f"*🤖 LLM Judge (Groq):*")
    lines.append(f"  Batch-evaluating {len(candidates)} items in 1 API call...")

    # Send progress so far before LLM calls (can be slow)
    await _send_to_admin(admin_chat, s.telegram_bot_token, "\n".join(lines))
    lines = []

    try:
        scored = await judge_items(candidates)
    except Exception as e:
        await _send_to_admin(admin_chat, s.telegram_bot_token, f"❌ LLM judge failed: {e}")
        return

    scored.sort(key=lambda x: x.score, reverse=True)
    lines.append(f"*🤖 LLM Results:*")
    lines.append(f"  Approved (≥85): {len(scored)} / {len(candidates)}")
    for item in scored[:5]:
        lines.append(f"  [{item.score}] {item.emoji} `{item.title[:50]}`")
        lines.append(f"         _{item.reason[:80]}_")
    lines.append("")

    if not scored:
        lines.append("❌ Nothing approved by LLM — try lowering MIN_SCORE or check GROQ_API_KEY")
        await _send_to_admin(admin_chat, s.telegram_bot_token, "\n".join(lines))
        return

    await _send_to_admin(admin_chat, s.telegram_bot_token, "\n".join(lines))

    # ── 5. Generate content + send top 5 previews ────────────────────────────
    images_dir = Path("./data/images")
    images_dir.mkdir(parents=True, exist_ok=True)

    await _send_to_admin(
        admin_chat, s.telegram_bot_token,
        f"📤 Sending top {min(5, len(scored))} previews with approve/skip buttons..."
    )

    for item in scored[:5]:
        content = await generate_content(item)
        if not content:
            continue
        card_path = images_dir / f"{content.website_slug}.png"
        card_desc = content.website_body_en[:160].split("\n")[0]
        generated = generate_card(
            title=content.website_title_en or item.title,
            description=card_desc,
            category=item.category.value,
            emoji=item.emoji,
            accent_color=item.accent_color,
            source=item.source.value,
            score=item.score,
            output_path=card_path,
        )
        if generated:
            content.image_path = str(generated)

        # Save as pending so approve/skip buttons work
        storage.save_pending(
            slug=content.website_slug,
            item_url=item.url,
            content_json=content.model_dump_json(),
            image_path=content.image_path,
        )
        await send_preview(content, storage)

    await _send_to_admin(
        admin_chat, s.telegram_bot_token,
        "✅ Done! Use ✅/❌ buttons above to approve or skip.\nRun `python -m app.bot` to handle button clicks."
    )


def _md_to_html(text: str) -> str:
    """Convert simple *bold* and `code` markdown to HTML for Telegram."""
    import re
    text = re.sub(r'\*([^*]+)\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)
    return text


async def _send_to_admin(admin_chat: str, bot_token: str, text: str) -> None:
    plain = text.replace("*", "").replace("`", "").replace("_", "")
    if not admin_chat or not bot_token:
        logger.info("[DRY RUN] " + plain)
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "chat_id": admin_chat,
                "text": _md_to_html(text)[:4000],
                "parse_mode": "HTML",
            })
            if resp.status_code != 200:
                # fallback: plain text
                logger.warning(f"Telegram HTML send failed ({resp.status_code}), retrying as plain text")
                await client.post(url, json={"chat_id": admin_chat, "text": plain[:4000]})
    except Exception as e:
        logger.error(f"Failed to send to admin: {e}")


def main():
    parser = argparse.ArgumentParser(description="TechRadar AI — Content Pipeline")
    parser.add_argument(
        "--source",
        choices=list(COLLECTOR_MAP.keys()) + ["all"],
        default="all",
        help="Data source (default: all)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run as a background scheduler daemon",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect + filter + LLM judge, send top 5 previews to admin — nothing published",
    )
    args = parser.parse_args()

    # Always show config warnings at startup
    for w in _check_config():
        logger.warning(w)

    if args.source == "all":
        collectors = [_load_collector(p) for p in COLLECTOR_MAP.values()]
    else:
        collectors = [_load_collector(COLLECTOR_MAP[args.source])]

    if args.schedule:
        from app.scheduler.scheduler import build_scheduler
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Scheduler started — press Ctrl+C to stop")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
    elif args.dry_run:
        logger.info(f"Starting DRY RUN with source='{args.source}'")
        asyncio.run(run_dry_run(collectors))
    else:
        from app.pipeline import run_pipeline
        logger.info(f"Running pipeline with source='{args.source}'")
        asyncio.run(run_pipeline(collectors))


if __name__ == "__main__":
    main()
