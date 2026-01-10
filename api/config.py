"""
Centralized configuration for Calendar Club API.

Uses environment variables with sensible defaults.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for agent conversations",
    )

    # Eventbrite Configuration
    eventbrite_api_key: str | None = Field(
        default=None,
        description="Eventbrite API key for event discovery",
    )

    # Application Mode
    demo_mode: bool = Field(
        default=False,
        description="When true, returns demo events instead of real API calls",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        """Check if running in production mode (has real API keys)."""
        return bool(self.openai_api_key and self.eventbrite_api_key)

    @property
    def can_search_events(self) -> bool:
        """Check if event search is available."""
        return self.demo_mode or bool(self.eventbrite_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


# Convenience function to check demo mode
def is_demo_mode() -> bool:
    """Check if running in demo mode."""
    return get_settings().demo_mode
