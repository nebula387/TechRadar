import httpx
import logging
import asyncio
from datetime import datetime
from app.models import RawItem, Source
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)
HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector(BaseCollector):
    source_name = "hackernews"

    async def collect(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{HN_API}/topstories.json")
                resp.raise_for_status()
                ids = resp.json()[:60]

                tasks = [self._fetch_story(client, sid) for sid in ids]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                items = [r for r in results if isinstance(r, RawItem)]
                logger.info(f"HackerNews: {len(items)} items collected")
                return items
        except Exception as e:
            logger.error(f"HackerNews failed: {e}")
            return []

    async def _fetch_story(self, client: httpx.AsyncClient, story_id: int) -> RawItem | None:
        try:
            resp = await client.get(f"{HN_API}/item/{story_id}.json")
            story = resp.json()
            if not story or story.get("type") != "story" or not story.get("url"):
                return None
            return RawItem(
                source=Source.HACKERNEWS,
                title=story.get("title", ""),
                url=story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                description=story.get("title", ""),
                stars=story.get("score", 0),
                author=story.get("by"),
                raw_data={"hn_id": story_id, "comments": story.get("descendants", 0)},
                collected_at=datetime.utcnow(),
            )
        except Exception:
            return None
