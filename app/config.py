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

    # GitHub
    github_token: str = ""

    # LLM — free tier only
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    openrouter_model: str = "mistralai/mistral-7b-instruct:free"

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
