import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from app.models import GeneratedContent, ScoredItem, Source, Category
from app.publishers.telegram import TelegramPublisher
from app.publishers.website import WebsitePublisher
from app.database.storage import Storage


def _scored_item() -> ScoredItem:
    return ScoredItem(
        source=Source.GITHUB,
        title="Amazing AI Tool",
        url="https://github.com/example/ai-tool",
        description="A revolutionary tool for AI development that dramatically improves workflow efficiency",
        stars=3000,
        raw_data={},
        collected_at=datetime.utcnow(),
        score=92,
        category=Category.DEVELOPER_TOOL,
        audience="ML Engineers",
        is_interesting=True,
        novelty=9,
        practical_value=9,
        wow_factor=8,
        reason="Genuinely novel approach to AI tooling",
        emoji="🚀",
        accent_color="#6366f1",
    )


def _content(image_path=None) -> GeneratedContent:
    return GeneratedContent(
        item=_scored_item(),
        telegram_text_ru="🚀 **Amazing AI Tool**\n\nРевол. инструмент.\nhttps://github.com/example/ai-tool",
        instagram_caption_en="Amazing AI tool! Link in bio 🔗",
        instagram_hashtags=["ai", "tech", "developer"],
        twitter_thread_en=[],
        linkedin_post_en="",
        reddit_title_en="Amazing AI Tool",
        reddit_body_en="Description of the amazing AI tool",
        website_title_en="Amazing AI Tool Changes How Engineers Work",
        website_body_en="Full article text here.\n\nSecond paragraph.",
        website_slug="20260101-amazing-ai-tool",
        tags=["ai", "developer", "python"],
        image_path=image_path,
    )


def test_telegram_disabled_without_credentials():
    publisher = TelegramPublisher()
    with patch("app.publishers.telegram.get_settings") as mock_settings:
        s = MagicMock()
        s.enable_telegram = True
        s.telegram_bot_token = ""
        s.telegram_channel_id = ""
        mock_settings.return_value = s
        assert not publisher.is_enabled


@pytest.mark.asyncio
async def test_telegram_publishes_text_message():
    publisher = TelegramPublisher()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": {"message_id": 42}}

    with patch("app.publishers.telegram.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        s = MagicMock()
        s.enable_telegram = True
        s.telegram_bot_token = "fake_token"
        s.telegram_channel_id = "@fake_channel"
        mock_settings.return_value = s

        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_resp)

        result = await publisher.publish(_content())

    assert result["message_id"] == 42


@pytest.mark.asyncio
async def test_website_publisher_creates_files(tmp_path):
    publisher = WebsitePublisher()
    content = _content()

    with patch("app.publishers.website.get_settings") as mock_settings:
        s = MagicMock()
        s.enable_website = True
        s.website_output_dir = str(tmp_path)
        s.website_base_url = "https://example.com"
        mock_settings.return_value = s

        result = await publisher.publish(content)

    post_file = tmp_path / "posts" / "20260101-amazing-ai-tool.html"
    index_file = tmp_path / "index.html"
    feed_file = tmp_path / "feed.json"

    assert post_file.exists(), "Post HTML file should be created"
    assert index_file.exists(), "Index HTML file should be created"
    assert feed_file.exists(), "feed.json should be created"
    assert "Amazing AI Tool Changes How Engineers Work" in post_file.read_text()
    assert "result" in result
