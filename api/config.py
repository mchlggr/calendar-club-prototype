"""Configuration management for Calendar Club API."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Required
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Event sources
    eventbrite_api_key: str = Field(default="", description="Eventbrite API key")
    exa_api_key: str = Field(default="", description="Exa API key for web search")
    firecrawl_api_key: str = Field(default="", description="Firecrawl API key for web scraping")

    # Google Calendar OAuth
    google_client_id: str = Field(default="", description="Google OAuth client ID")
    google_client_secret: str = Field(default="", description="Google OAuth client secret")
    google_redirect_uri: str = Field(
        default="http://localhost:3000/auth/google/callback",
        description="Google OAuth redirect URI",
    )

    # Meetup OAuth
    meetup_client_id: str = Field(default="", description="Meetup OAuth client ID")
    meetup_client_secret: str = Field(default="", description="Meetup OAuth client secret")
    meetup_access_token: str = Field(default="", description="Meetup OAuth access token")

    # Server config
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated CORS origins",
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # Observability
    hyperdx_api_key: str = Field(default="", description="HyperDX API key")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin]

    @property
    def has_event_source(self) -> bool:
        """Check if any event source is configured."""
        return bool(self.eventbrite_api_key) or bool(self.exa_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def configure_logging(settings: Settings | None = None) -> None:
    """Configure application logging."""
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)  # Suppresses openai._base_client, openai.agents, etc.
