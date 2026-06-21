import httpx
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup
from app.models import RawItem, Source
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TechRadarBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

SINCE_OPTIONS = ["daily", "weekly"]


class GitHubTrendingCollector(BaseCollector):
    source_name = "github_trending"

    async def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for since in SINCE_OPTIONS:
                try:
                    resp = await client.get(
                        TRENDING_URL,
                        headers=HEADERS,
                        params={"since": since},
                    )
                    resp.raise_for_status()
                    parsed = self._parse_trending(resp.text, since)
                    for item in parsed:
                        if item.url not in seen_urls:
                            seen_urls.add(item.url)
                            items.append(item)
                except Exception as e:
                    logger.error(f"GitHub trending ({since}) fetch failed: {e}")

        logger.info(f"GitHub Trending: {len(items)} items collected")
        return items

    def _parse_trending(self, html: str, since: str) -> list[RawItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[RawItem] = []

        for article in soup.select("article.Box-row"):
            try:
                item = self._parse_article(article, since)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug(f"Failed to parse trending article: {e}")

        return items

    def _parse_article(self, article, since: str) -> RawItem | None:
        # Repo path e.g. /owner/repo
        h2 = article.select_one("h2 a")
        if not h2:
            return None
        repo_path = h2.get("href", "").strip().lstrip("/")
        if not repo_path or "/" not in repo_path:
            return None
        url = f"https://github.com/{repo_path}"

        # Description
        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Total stars
        stars_el = article.select_one("a[href$='/stargazers']")
        stars = 0
        if stars_el:
            stars_text = stars_el.get_text(strip=True).replace(",", "")
            try:
                stars = int(stars_text)
            except ValueError:
                pass

        # Stars today / this week
        stars_today = 0
        today_el = article.select_one("span.d-inline-block.float-sm-right")
        if today_el:
            text = today_el.get_text(strip=True)
            match = re.search(r"([\d,]+)\s+stars", text)
            if match:
                stars_today = int(match.group(1).replace(",", ""))

        # Language
        lang_el = article.select_one("span[itemprop='programmingLanguage']")
        language = lang_el.get_text(strip=True) if lang_el else None

        # Built by (contributors)
        built_by = article.select("a[data-hovercard-type='user']")
        authors = [a.get("href", "").lstrip("/") for a in built_by[:3]]

        title = repo_path
        if not description or len(description) < 10:
            return None  # skip repos without description

        return RawItem(
            source=Source.GITHUB,
            title=title,
            url=url,
            description=description,
            stars=stars,
            language=language,
            author=authors[0] if authors else repo_path.split("/")[0],
            raw_data={
                "stars_today": stars_today,
                "stars_this_week": stars_today if since == "weekly" else 0,
                "trending_since": since,
                "contributors": authors,
            },
            collected_at=datetime.utcnow(),
        )
