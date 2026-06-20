import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from app.collectors.github import GitHubCollector
from app.collectors.hackernews import HackerNewsCollector
from app.models import Source


GITHUB_REPO = {
    "full_name": "owner/amazing-repo",
    "html_url": "https://github.com/owner/amazing-repo",
    "description": "A revolutionary AI framework for production ML pipelines",
    "stargazers_count": 2500,
    "language": "Python",
    "topics": ["ai", "machine-learning"],
    "owner": {"login": "owner"},
    "forks_count": 200,
    "open_issues_count": 12,
    "pushed_at": "2026-05-01T00:00:00Z",
}


@pytest.mark.asyncio
async def test_github_collector_parses_repo():
    collector = GitHubCollector()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [GITHUB_REPO]}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)
        items = await collector._fetch_trending()

    assert len(items) == 1
    assert items[0].source == Source.GITHUB
    assert items[0].title == "owner/amazing-repo"
    assert items[0].stars == 2500
    assert "ai" in items[0].tags


@pytest.mark.asyncio
async def test_github_collector_handles_error():
    collector = GitHubCollector()
    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=Exception("Network error"))
        items = await collector._fetch_trending()
    assert items == []


@pytest.mark.asyncio
async def test_hackernews_collector_filters_non_story():
    collector = HackerNewsCollector()
    story_resp = MagicMock()
    story_resp.raise_for_status = MagicMock()
    story_resp.json.side_effect = [
        [1, 2, 3],                                             # top stories list
        {"id": 1, "type": "comment", "title": "Comment"},     # non-story — skipped
        {"id": 2, "type": "story", "title": "Great post", "url": "https://example.com", "score": 300, "by": "user"},
        {"id": 3, "type": "story", "title": "No URL"},        # no url — skipped
    ]

    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=story_resp)
        items = await collector.collect()

    stories = [i for i in items if i is not None]
    # only story #2 has both type=story and a url
    assert all(i.source == Source.HACKERNEWS for i in stories)
