import httpx
import logging
from pathlib import Path
from app.models import GeneratedContent
from app.publishers.base import BasePublisher
from app.config import get_settings

logger = logging.getLogger(__name__)


class TelegramPublisher(BasePublisher):
    channel_name = "telegram"

    @property
    def is_enabled(self) -> bool:
        s = get_settings()
        return s.enable_telegram and bool(s.telegram_bot_token) and bool(s.telegram_channel_id)

    async def publish(self, content: GeneratedContent) -> dict:
        s = get_settings()
        base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
        channel = s.telegram_channel_id
        image_path = Path(content.image_path) if content.image_path else None

        async with httpx.AsyncClient(timeout=30) as client:
            if image_path and image_path.exists():
                with open(image_path, "rb") as f:
                    resp = await client.post(
                        f"{base}/sendPhoto",
                        data={
                            "chat_id": channel,
                            "caption": content.telegram_text_ru[:1024],
                            "parse_mode": "Markdown",
                        },
                        files={"photo": ("card.png", f, "image/png")},
                    )
            else:
                resp = await client.post(
                    f"{base}/sendMessage",
                    json={
                        "chat_id": channel,
                        "text": content.telegram_text_ru,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    },
                )
            resp.raise_for_status()
            msg_id = resp.json().get("result", {}).get("message_id")
            logger.info(f"Telegram published: message_id={msg_id}")
            return {"message_id": msg_id}
