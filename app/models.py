from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class Source(str, Enum):
    GITHUB = "github"
    HUGGINGFACE = "huggingface"
    PRODUCTHUNT = "producthunt"
    HACKERNEWS = "hackernews"
    ARXIV = "arxiv"


class Category(str, Enum):
    DEVELOPER_TOOL = "Developer Tool"
    AI_MODEL = "AI Model"
    RESEARCH_PAPER = "Research Paper"
    OPEN_SOURCE = "Open Source"
    AI_AGENT = "AI Agent"
    MCP_SERVER = "MCP Server"
    DATASET = "Dataset"


class RawItem(BaseModel):
    source: Source
    title: str
    url: str
    description: str
    stars: int | None = None
    language: str | None = None
    tags: list[str] = []
    author: str | None = None
    raw_data: dict = {}
    collected_at: datetime


class ScoredItem(RawItem):
    score: int                   # 0–100 (only items >= 85 get published)
    category: Category
    audience: str
    is_interesting: bool
    novelty: int                 # 0–10
    practical_value: int         # 0–10
    wow_factor: int              # 0–10
    reason: str
    rejection_reason: str | None = None
    emoji: str
    accent_color: str            # hex color for card


class GeneratedContent(BaseModel):
    item: ScoredItem
    telegram_text_ru: str
    instagram_caption_en: str
    instagram_hashtags: list[str]
    twitter_thread_en: list[str]
    linkedin_post_en: str
    reddit_title_en: str
    reddit_body_en: str
    website_title_en: str
    website_body_en: str
    website_slug: str
    tags: list[str]
    image_path: str | None = None


class PublishedRecord(BaseModel):
    item_url: str
    source: Source
    score: int
    published_at: datetime
    channels: list[str]
    telegram_message_id: int | None = None
    instagram_post_id: str | None = None
    reddit_post_id: str | None = None
    tweet_id: str | None = None
