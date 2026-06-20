import httpx
import asyncio
import logging
from app.models import GeneratedContent
from app.publishers.base import BasePublisher
from app.config import get_settings

logger = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v18.0"


class InstagramPublisher(BasePublisher):
    channel_name = "instagram"

    @property
    def is_enabled(self) -> bool:
        s = get_settings()
        return s.enable_instagram and bool(s.instagram_access_token) and bool(s.instagram_account_id)

    async def publish(self, content: GeneratedContent) -> dict:
        s = get_settings()
        account_id = s.instagram_account_id
        token = s.instagram_access_token

        # Build caption with hashtags
        hashtags = " ".join(f"#{tag}" for tag in content.instagram_hashtags[:10])
        caption = f"{content.instagram_caption_en}\n\n{hashtags}"[:2200]

        # Image must be publicly accessible — served from the deployed website
        if not content.image_path:
            raise ValueError("Instagram requires an image card")
        image_url = f"{s.website_base_url}/images/{content.website_slug}.png"

        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Create media container
            r1 = await client.post(
                f"{GRAPH}/{account_id}/media",
                params={"image_url": image_url, "caption": caption, "access_token": token},
            )
            r1.raise_for_status()
            container_id = r1.json()["id"]
            logger.info(f"Instagram container created: {container_id}")

            # Wait for media processing
            await asyncio.sleep(8)

            # Step 2: Publish container
            r2 = await client.post(
                f"{GRAPH}/{account_id}/media_publish",
                params={"creation_id": container_id, "access_token": token},
            )
            r2.raise_for_status()
            post_id = r2.json()["id"]
            logger.info(f"Instagram published: post_id={post_id}")
            return {"post_id": post_id}
