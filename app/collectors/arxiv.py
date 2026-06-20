import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from app.models import RawItem, Source
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)
ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivCollector(BaseCollector):
    source_name = "arxiv"

    async def collect(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    ARXIV_API,
                    params={
                        "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
                        "start": 0,
                        "max_results": 25,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                resp.raise_for_status()
                items = self._parse_feed(resp.text)
                logger.info(f"ArXiv: {len(items)} items collected")
                return items
        except Exception as e:
            logger.error(f"ArXiv failed: {e}")
            return []

    def _parse_feed(self, xml_text: str) -> list[RawItem]:
        root = ET.fromstring(xml_text)
        items = []
        for entry in root.findall("atom:entry", NS):
            title_el = entry.find("atom:title", NS)
            summary_el = entry.find("atom:summary", NS)
            id_el = entry.find("atom:id", NS)
            if title_el is None or id_el is None:
                continue
            authors = [
                a.find("atom:name", NS).text
                for a in entry.findall("atom:author", NS)
                if a.find("atom:name", NS) is not None
            ]
            categories = [c.get("term", "") for c in entry.findall("atom:category", NS)]
            items.append(RawItem(
                source=Source.ARXIV,
                title=(title_el.text or "").strip().replace("\n", " "),
                url=(id_el.text or "").strip(),
                description=(summary_el.text or "").strip()[:500] if summary_el is not None else "",
                tags=categories[:5],
                author=", ".join(authors[:3]),
                raw_data={"categories": categories},
                collected_at=datetime.utcnow(),
            ))
        return items
