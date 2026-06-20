import httpx
import logging
from datetime import datetime
from app.models import RawItem, Source
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class ProductHuntCollector(BaseCollector):
    source_name = "producthunt"

    async def collect(self) -> list[RawItem]:
        # ProductHunt GraphQL API (public, no auth for basic queries)
        query = """
        {
          posts(order: VOTES, first: 20) {
            edges {
              node {
                id
                name
                tagline
                votesCount
                url
                website
                topics { edges { node { name } } }
              }
            }
          }
        }
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.producthunt.com/v2/api/graphql",
                    json={"query": query},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                edges = data.get("data", {}).get("posts", {}).get("edges", [])
                items = []
                for edge in edges:
                    post = edge["node"]
                    topics = [
                        t["node"]["name"]
                        for t in post.get("topics", {}).get("edges", [])
                    ]
                    items.append(RawItem(
                        source=Source.PRODUCTHUNT,
                        title=post.get("name", ""),
                        url=post.get("url") or post.get("website") or "",
                        description=post.get("tagline", ""),
                        stars=post.get("votesCount", 0),
                        tags=topics,
                        raw_data=post,
                        collected_at=datetime.utcnow(),
                    ))
                logger.info(f"ProductHunt: {len(items)} items collected")
                return items
        except Exception as e:
            logger.error(f"ProductHunt failed: {e}")
            return []
