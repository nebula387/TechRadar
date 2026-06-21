"""
Telegram approval bot for TechRadar AI.

Usage:
  python -m app.bot               # run polling loop (handles approve/skip)
  python -m app.bot --send        # send all pending previews to admin
  python -m app.bot --pending     # list pending items in console

The bot sends content previews to TELEGRAM_ADMIN_CHAT_ID with inline buttons.
Admin clicks ✅ Опубликовать or ❌ Пропустить — bot handles the callback.
"""

import asyncio
import json
import logging
import sys
import time
import argparse
from pathlib import Path

Path("./data").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

import httpx
from app.config import get_settings
from app.database.storage import Storage
from app.models import GeneratedContent


# ── Telegram API helpers ──────────────────────────────────────────────────────

def _tg_url(method: str) -> str:
    return f"https://api.telegram.org/bot{get_settings().telegram_bot_token}/{method}"


async def _tg_post(method: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_tg_url(method), **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _answer_callback(callback_id: str, text: str = "") -> None:
    try:
        await _tg_post("answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})
    except Exception as e:
        logger.debug(f"answerCallbackQuery failed: {e}")


async def _edit_message_reply_markup(chat_id: str, message_id: int, text_suffix: str) -> None:
    try:
        await _tg_post("editMessageReplyMarkup", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception:
        pass


# ── Preview builder ───────────────────────────────────────────────────────────

def _build_preview_text(content: GeneratedContent) -> str:
    item = content.item
    lines = [
        f"📋 *Превью для одобрения*",
        f"",
        f"*{item.emoji} {item.title}*",
        f"",
        f"🏷 Категория: {item.category.value}",
        f"⭐ Score: {item.score}/100  |  Novelty: {item.novelty}  |  Wow: {item.wow_factor}",
        f"👥 Аудитория: {item.audience}",
        f"",
        f"📝 *Причина:* {item.reason}",
        f"",
        f"─────────────────",
        f"🇷🇺 *Telegram пост:*",
        f"{content.telegram_text_ru[:600]}",
        f"─────────────────",
        f"🌐 *Заголовок сайта:*",
        f"{content.website_title_en}",
        f"",
        f"🔗 {item.url}",
    ]
    return "\n".join(lines)


def _build_keyboard(slug: str) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"approve:{slug}"},
            {"text": "❌ Пропустить",   "callback_data": f"skip:{slug}"},
        ]]
    }


# ── Send preview to admin ─────────────────────────────────────────────────────

async def send_preview(content: GeneratedContent, storage: Storage) -> int | None:
    s = get_settings()
    admin_chat = s.telegram_admin_chat_id
    if not admin_chat:
        logger.warning("TELEGRAM_ADMIN_CHAT_ID not set — cannot send preview")
        return None

    slug = content.website_slug
    text = _build_preview_text(content)
    keyboard = _build_keyboard(slug)
    image_path = Path(content.image_path) if content.image_path else None

    try:
        if image_path and image_path.exists():
            with open(image_path, "rb") as f:
                resp = await _tg_post(
                    "sendPhoto",
                    data={"chat_id": admin_chat, "caption": text[:1024], "parse_mode": "Markdown"},
                    files={"photo": ("card.png", f, "image/png")},
                )
            # Send keyboard as separate message because sendPhoto doesn't support complex keyboards easily
            msg_resp = await _tg_post("sendMessage", json={
                "chat_id": admin_chat,
                "text": text[1024:2000] if len(text) > 1024 else f"👆 Выбери действие для: *{content.item.title[:60]}*",
                "parse_mode": "Markdown",
                "reply_markup": keyboard,
            })
        else:
            msg_resp = await _tg_post("sendMessage", json={
                "chat_id": admin_chat,
                "text": text[:4000],
                "parse_mode": "Markdown",
                "reply_markup": keyboard,
            })

        message_id = msg_resp.get("result", {}).get("message_id")
        storage.set_preview_message_id(slug, message_id)
        logger.info(f"Preview sent for '{slug}': message_id={message_id}")
        return message_id
    except Exception as e:
        logger.error(f"Failed to send preview for '{slug}': {e}")
        return None


# ── Publish approved item ─────────────────────────────────────────────────────

async def publish_approved(slug: str, storage: Storage) -> list[str]:
    from app.pipeline import _publish_to_all

    row = storage.get_pending_by_slug(slug)
    if not row:
        logger.error(f"Pending item '{slug}' not found")
        return []

    content = GeneratedContent.model_validate_json(row["content_json"])
    if row.get("image_path"):
        content.image_path = row["image_path"]

    channels = await _publish_to_all(content, storage)
    if channels:
        storage.set_pending_status(slug, "published")
        logger.info(f"Published '{slug}' to {channels}")
    return channels


# ── Polling loop ──────────────────────────────────────────────────────────────

async def poll_loop(timeout_seconds: int = 0) -> None:
    """
    Poll Telegram for callback_query updates.
    timeout_seconds=0 means run forever.
    """
    s = get_settings()
    storage = Storage(s.database_url)
    admin_chat = s.telegram_admin_chat_id

    offset = 0
    start = time.monotonic()
    logger.info(f"Bot polling started (timeout={timeout_seconds}s, 0=forever)")

    while True:
        if timeout_seconds > 0 and (time.monotonic() - start) > timeout_seconds:
            pending = storage.get_all_pending()
            if pending:
                logger.info(f"Timeout reached — {len(pending)} item(s) remain pending (not auto-published)")
            logger.info("Polling loop ended")
            break

        try:
            data = await _tg_post("getUpdates", json={
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["callback_query", "message"],
            })
        except Exception as e:
            logger.error(f"getUpdates error: {e}")
            await asyncio.sleep(5)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1

            # Handle inline button click
            if "callback_query" in update:
                cq = update["callback_query"]
                cq_id = cq["id"]
                cq_data = cq.get("data", "")
                cq_chat = str(cq["message"]["chat"]["id"])

                # Security: only accept from admin
                if cq_chat != str(admin_chat):
                    await _answer_callback(cq_id, "⛔ Не авторизован")
                    continue

                if ":" not in cq_data:
                    continue
                action, slug = cq_data.split(":", 1)

                row = storage.get_pending_by_slug(slug)
                if not row or row["status"] != "pending":
                    await _answer_callback(cq_id, "⚠️ Уже обработано")
                    await _edit_message_reply_markup(cq_chat, cq["message"]["message_id"], "")
                    continue

                if action == "approve":
                    await _answer_callback(cq_id, "⏳ Публикую...")
                    await _edit_message_reply_markup(cq_chat, cq["message"]["message_id"], "")
                    channels = await publish_approved(slug, storage)
                    status_text = f"✅ Опубликовано → {', '.join(channels)}" if channels else "⚠️ Ошибка публикации"
                    await _tg_post("sendMessage", json={"chat_id": admin_chat, "text": status_text})

                elif action == "skip":
                    await _answer_callback(cq_id, "⏭ Пропущено")
                    await _edit_message_reply_markup(cq_chat, cq["message"]["message_id"], "")
                    storage.set_pending_status(slug, "skipped")
                    await _tg_post("sendMessage", json={"chat_id": admin_chat, "text": f"⏭ Пропущено: {slug}"})

            # Handle /pending command
            elif "message" in update:
                msg = update["message"]
                msg_chat = str(msg["chat"]["id"])
                text = msg.get("text", "")

                if msg_chat != str(admin_chat):
                    continue

                if text.startswith("/pending"):
                    rows = storage.get_all_pending()
                    if not rows:
                        await _tg_post("sendMessage", json={"chat_id": admin_chat, "text": "✅ Нет ожидающих публикаций"})
                    else:
                        lines = [f"📋 Ожидают одобрения: {len(rows)}"]
                        for r in rows:
                            c = GeneratedContent.model_validate_json(r["content_json"])
                            lines.append(f"\n• [{c.item.score}] {c.item.emoji} {c.item.title[:60]}")
                            lines.append(f"  Slug: `{r['slug']}`")
                        await _tg_post("sendMessage", json={
                            "chat_id": admin_chat,
                            "text": "\n".join(lines),
                            "parse_mode": "Markdown",
                        })

                elif text.startswith("/send_previews"):
                    rows = storage.get_all_pending()
                    for r in rows:
                        content = GeneratedContent.model_validate_json(r["content_json"])
                        if r.get("image_path"):
                            content.image_path = r["image_path"]
                        await send_preview(content, storage)
                    await _tg_post("sendMessage", json={
                        "chat_id": admin_chat,
                        "text": f"📤 Отправлено превью: {len(rows)} шт.",
                    })

        await asyncio.sleep(1)


# ── CLI entry ─────────────────────────────────────────────────────────────────

async def _cmd_list_pending():
    s = get_settings()
    storage = Storage(s.database_url)
    rows = storage.get_all_pending()
    if not rows:
        print("Нет ожидающих публикаций")
        return
    print(f"\n📋 Ожидают одобрения: {len(rows)}\n")
    for r in rows:
        c = GeneratedContent.model_validate_json(r["content_json"])
        print(f"  [{c.item.score}] {c.item.emoji} {c.item.title}")
        print(f"  Slug: {r['slug']}")
        print(f"  Status: {r['status']}")
        print()


async def _cmd_send_previews():
    s = get_settings()
    storage = Storage(s.database_url)
    rows = storage.get_all_pending()
    if not rows:
        print("Нет ожидающих публикаций для отправки")
        return
    for r in rows:
        content = GeneratedContent.model_validate_json(r["content_json"])
        if r.get("image_path"):
            content.image_path = r["image_path"]
        await send_preview(content, storage)
    print(f"Отправлено превью: {len(rows)} шт.")


async def _cmd_test():
    s = get_settings()
    if not s.telegram_bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return
    if not s.telegram_admin_chat_id:
        print("❌ TELEGRAM_ADMIN_CHAT_ID not set — don't know where to send the test")
        return

    # Check bot identity
    try:
        me = await _tg_post("getMe")
        bot_name = me.get("result", {}).get("username", "?")
        print(f"✅ Bot connected: @{bot_name}")
    except Exception as e:
        print(f"❌ Bot connection failed: {e}")
        return

    # Send test message
    try:
        resp = await _tg_post("sendMessage", json={
            "chat_id": s.telegram_admin_chat_id,
            "text": (
                "✅ *TechRadar AI — Bot connected!*\n\n"
                "Бот работает и может отправлять тебе превью.\n\n"
                "Следующий шаг:\n"
                "`python -m app.main --dry-run --source github`\n"
                "→ соберёт GitHub, пройдёт фильтрацию и пришлёт топ 5."
            ),
            "parse_mode": "Markdown",
        })
        msg_id = resp.get("result", {}).get("message_id")
        print(f"✅ Test message sent to admin (message_id={msg_id})")
        print(f"   Check Telegram chat ID: {s.telegram_admin_chat_id}")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")
        print(f"   Check TELEGRAM_ADMIN_CHAT_ID={s.telegram_admin_chat_id!r}")


def _normalize_channel_id(channel_id: str) -> str:
    """Convert t.me/name or plain name to @name for Bot API."""
    cid = channel_id.strip()
    if cid.startswith("https://t.me/"):
        cid = "@" + cid[len("https://t.me/"):]
    elif cid.startswith("t.me/"):
        cid = "@" + cid[len("t.me/"):]
    elif cid and not cid.startswith("@") and not cid.startswith("-"):
        cid = "@" + cid
    return cid


async def _cmd_clear_channel(up_to: int = 300) -> None:
    """Delete messages 1..up_to from the channel. Silently skips non-existent IDs."""
    s = get_settings()
    if not s.telegram_channel_id:
        print("❌ TELEGRAM_CHANNEL_ID not set")
        return

    channel_id = _normalize_channel_id(s.telegram_channel_id)
    print(f"Channel ID: {channel_id}")

    # Check bot permissions first
    async with httpx.AsyncClient(timeout=10) as client:
        me = await client.post(_tg_url("getMe"))
        bot_id = me.json().get("result", {}).get("id")
        chat_resp = await client.post(_tg_url("getChatMember"), json={"chat_id": channel_id, "user_id": bot_id})
        chat_data = chat_resp.json()
        if not chat_data.get("ok"):
            print(f"❌ Can't check bot status: {chat_data.get('description')}")
            print("   Make sure the bot is an admin of the channel with 'Delete messages' permission")
            return
        status = chat_data.get("result", {}).get("status")
        can_delete = chat_data.get("result", {}).get("can_delete_messages", False)
        print(f"Bot status in channel: {status}, can_delete_messages: {can_delete}")
        if status not in ("administrator", "creator") or not can_delete:
            print("❌ Bot is not an admin or doesn't have 'Delete messages' permission")
            print("   Go to channel → Edit → Administrators → add your bot → enable 'Delete messages'")
            return

    deleted = 0
    print(f"Deleting messages 1–{up_to} from {channel_id} ...")
    async with httpx.AsyncClient(timeout=10) as client:
        for msg_id in range(1, up_to + 1):
            try:
                resp = await client.post(
                    _tg_url("deleteMessage"),
                    json={"chat_id": channel_id, "message_id": msg_id},
                )
                if resp.json().get("ok"):
                    deleted += 1
                    print(f"  ✓ deleted message_id={msg_id}")
            except Exception:
                pass
            if msg_id % 20 == 0:
                await asyncio.sleep(1)

    print(f"\nDone: {deleted} messages deleted")


def main():
    parser = argparse.ArgumentParser(description="TechRadar AI — Approval Bot")
    parser.add_argument("--test",          action="store_true", help="Send a test message to verify bot connection")
    parser.add_argument("--send",          action="store_true", help="Send all pending previews to admin")
    parser.add_argument("--pending",       action="store_true", help="List pending items in console")
    parser.add_argument("--clear-channel", action="store_true", help="Delete all messages from the Telegram channel")
    parser.add_argument("--up-to",         type=int, default=300, help="Max message_id to try deleting (default: 300)")
    parser.add_argument("--timeout",       type=int, default=0, help="Polling timeout in seconds (0=forever)")
    args = parser.parse_args()

    s = get_settings()
    if not s.telegram_bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    if args.test:
        asyncio.run(_cmd_test())
    elif args.pending:
        asyncio.run(_cmd_list_pending())
    elif args.send:
        asyncio.run(_cmd_send_previews())
    elif args.clear_channel:
        asyncio.run(_cmd_clear_channel(up_to=args.up_to))
    else:
        asyncio.run(poll_loop(timeout_seconds=args.timeout))


if __name__ == "__main__":
    main()
