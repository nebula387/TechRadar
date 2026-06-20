import httpx
import logging
from datetime import datetime
from app.models import RawItem, Source
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)
HF_API = "https://huggingface.co/api"


class HuggingFaceCollector(BaseCollector):
    source_name = "huggingface"

    async def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        items.extend(await self._fetch_models())
        items.extend(await self._fetch_spaces())
        return items

    async def _fetch_models(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HF_API}/models",
                    params={"sort": "trending", "limit": 30, "full": "false"},
                )
                resp.raise_for_status()
                items = []
                for m in resp.json():
                    desc = (
                        m.get("description")
                        or (m.get("cardData") or {}).get("summary", "")
                        or ""
                    )
                    items.append(RawItem(
                        source=Source.HUGGINGFACE,
                        title=m.get("modelId", ""),
                        url=f"https://huggingface.co/{m.get('modelId', '')}",
                        description=desc,
                        stars=m.get("likes", 0),
                        tags=m.get("tags", []),
                        author=m.get("author"),
                        raw_data={"downloads": m.get("downloads", 0)},
                        collected_at=datetime.utcnow(),
                    ))
                logger.info(f"HuggingFace models: {len(items)} items")
                return items
        except Exception as e:
            logger.error(f"HuggingFace models failed: {e}")
            return []

    async def _fetch_spaces(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HF_API}/spaces",
                    params={"sort": "trending", "limit": 20},
                )
                resp.raise_for_status()
                items = []
                for s in resp.json():
                    items.append(RawItem(
                        source=Source.HUGGINGFACE,
                        title=f"[Space] {s.get('id', '')}",
                        url=f"https://huggingface.co/spaces/{s.get('id', '')}",
                        description=(s.get("cardData") or {}).get("title", "") or s.get("id", ""),
                        stars=s.get("likes", 0),
                        tags=s.get("tags", []),
                        author=s.get("author"),
                        raw_data={},
                        collected_at=datetime.utcnow(),
                    ))
                logger.info(f"HuggingFace spaces: {len(items)} items")
                return items
        except Exception as e:
            logger.error(f"HuggingFace spaces failed: {e}")
            return []
