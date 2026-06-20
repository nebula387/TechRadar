import httpx
import logging
from datetime import datetime
from app.models import RawItem, Source
from app.collectors.base import BaseCollector
from app.config import get_settings

logger = logging.getLogger(__name__)
GH_API = "https://api.github.com"


class GitHubCollector(BaseCollector):
    source_name = "github"

    async def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        items.extend(await self._fetch_trending())
        items.extend(await self._search_topics())
        seen = {i.url for i in items}
        return list({i.url: i for i in items}.values())  # dedup by url

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = get_settings().github_token
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def _fetch_trending(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{GH_API}/search/repositories",
                    headers=self._headers(),
                    params={
                        "q": "stars:>500 pushed:>2025-01-01 topic:ai OR topic:llm OR topic:machine-learning",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 30,
                    },
                )
                resp.raise_for_status()
                items = [self._parse_repo(r) for r in resp.json().get("items", [])]
                logger.info(f"GitHub trending: {len(items)} items")
                return items
        except Exception as e:
            logger.error(f"GitHub trending failed: {e}")
            return []

    async def _search_topics(self) -> list[RawItem]:
        queries = [
            "topic:ai-agent stars:>200",
            "topic:mcp-server stars:>100",
            "topic:local-llm stars:>300",
        ]
        items: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for q in queries:
                    resp = await client.get(
                        f"{GH_API}/search/repositories",
                        headers=self._headers(),
                        params={"q": q, "sort": "stars", "order": "desc", "per_page": 10},
                    )
                    if resp.status_code == 200:
                        items.extend(self._parse_repo(r) for r in resp.json().get("items", []))
        except Exception as e:
            logger.error(f"GitHub topic search failed: {e}")
        logger.info(f"GitHub topic search: {len(items)} items")
        return items

    def _parse_repo(self, repo: dict) -> RawItem:
        return RawItem(
            source=Source.GITHUB,
            title=repo["full_name"],
            url=repo["html_url"],
            description=repo.get("description") or "",
            stars=repo.get("stargazers_count"),
            language=repo.get("language"),
            tags=repo.get("topics", []),
            author=repo.get("owner", {}).get("login"),
            raw_data={
                "forks": repo.get("forks_count"),
                "open_issues": repo.get("open_issues_count"),
                "pushed_at": repo.get("pushed_at"),
            },
            collected_at=datetime.utcnow(),
        )
