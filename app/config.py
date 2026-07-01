from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    # Your personal Telegram chat ID (get from @userinfobot)
    telegram_admin_chat_id: str = ""
    # If true: pipeline sends previews to admin for approval before publishing
    enable_approval_mode: bool = False
    # Seconds to wait for admin response before auto-skipping (0 = wait forever)
    approval_timeout_seconds: int = 600

    # GitHub
    github_token: str = ""

    # LLM — free tier only
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.6-27b"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-2-9b-it:free"
    # NVIDIA NIM — fallback for Groq filtering (free credits on signup)
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.3-70b-instruct"

    # Instagram (Meta Graph API)
    instagram_access_token: str = ""
    instagram_account_id: str = ""

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_password: str = ""

    # Twitter / X
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    # LinkedIn
    linkedin_access_token: str = ""

    # Quality
    min_score: int = 85
    max_posts_per_day: int = 3
    max_telegram_posts_per_day: int = 1

    # Channels
    enable_telegram: bool = True
    enable_instagram: bool = False
    enable_website: bool = True
    enable_reddit: bool = False
    enable_twitter: bool = False
    enable_linkedin: bool = False

    # Website
    website_output_dir: str = "./website/public"
    website_base_url: str = "https://nebula387.github.io/TechRadar"

    # Database
    database_url: str = "./data/techradar.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
