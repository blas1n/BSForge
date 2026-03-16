"""Application configuration using Pydantic Settings.

This module defines all application configuration loaded from environment variables.
Configuration is validated at startup and provides type-safe access throughout the app.
"""

import secrets
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration.

    All configuration is loaded from environment variables or .env file.
    Validation happens automatically via Pydantic.

    Example:
        >>> config = Config()
        >>> print(config.app_name)
        'BSForge'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================
    # Application Settings
    # ============================================
    app_name: str = Field(default="BSForge", description="Application name")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Application environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    # ============================================
    # Database Settings
    # ============================================
    database_url: str = Field(
        default="postgresql+asyncpg://bsforge:bsforge_password@localhost:5432/bsforge",
        description="Async PostgreSQL connection URL",
    )
    database_url_sync: str = Field(
        default="postgresql://bsforge:bsforge_password@localhost:5432/bsforge",
        description="Sync PostgreSQL connection URL (for Alembic)",
    )
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    database_pool_size: int = Field(default=5, description="Connection pool size", ge=1, le=50)
    database_max_overflow: int = Field(
        default=10, description="Max overflow connections", ge=0, le=50
    )

    # ============================================
    # Security Settings
    # ============================================
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Application secret key",
    )

    # ============================================
    # LLM & AI APIs
    # ============================================
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")
    gemini_api_key: str = Field(default="", description="Google Gemini API key")

    # LLM Model Settings (LiteLLM format: provider/model-name)
    # Lightweight tasks (translation, classification, content classification)
    llm_model_light: str = Field(
        default="anthropic/claude-haiku-4-5-20251001",
        description="LLM model for lightweight tasks (translation, classification)",
    )
    llm_model_light_max_tokens: int = Field(
        default=500, description="Max tokens for lightweight LLM tasks", ge=100, le=2000
    )

    # Heavy tasks (script generation)
    llm_model_heavy: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="LLM model for heavy tasks (script generation)",
    )
    llm_model_heavy_max_tokens: int = Field(
        default=2000, description="Max tokens for heavy LLM tasks", ge=500, le=8000
    )

    # ============================================
    # YouTube API
    # ============================================
    google_client_id: str = Field(default="", description="Google OAuth client ID")
    google_client_secret: str = Field(default="", description="Google OAuth client secret")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/google/callback", description="OAuth redirect URI"
    )
    youtube_credentials_path: str = Field(
        default="config/youtube_credentials.json",
        description="Path to YouTube OAuth credentials file",
    )
    youtube_token_path: str = Field(
        default="config/youtube_token.pickle",
        description="Path to YouTube OAuth token file",
    )

    # ============================================
    # Text-to-Speech
    # ============================================
    edge_tts_enabled: bool = Field(default=True, description="Enable Edge TTS")
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key")
    elevenlabs_enabled: bool = Field(default=False, description="Enable ElevenLabs TTS")

    # ============================================
    # Content Sources
    # ============================================
    reddit_client_id: str = Field(default="", description="Reddit client ID")
    reddit_client_secret: str = Field(default="", description="Reddit client secret")
    reddit_user_agent: str = Field(default="BSForge/1.0", description="Reddit user agent")
    pexels_api_key: str = Field(default="", description="Pexels API key")

    # ============================================
    # File Storage
    # ============================================
    storage_type: Literal["local", "s3"] = Field(default="local", description="Storage type")
    local_storage_path: str = Field(default="./outputs", description="Local storage path")

    # ============================================
    # Feature Flags
    # ============================================
    enable_auto_upload: bool = Field(default=False, description="Enable auto upload")

    # ============================================
    # Orchestrator
    # ============================================
    scheduler_interval_hours: int = Field(
        default=6, description="Hours between orchestrator runs", ge=1, le=168
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses asyncpg driver.

        Args:
            v: Database URL string

        Returns:
            Validated database URL

        Raises:
            ValueError: If URL doesn't use asyncpg driver
        """
        if isinstance(v, str) and not v.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use asyncpg driver (postgresql+asyncpg://)")
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode.

        Returns:
            True if app_env is 'development'
        """
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode.

        Returns:
            True if app_env is 'production'
        """
        return self.app_env == "production"


# =============================================================================
# Singleton accessor
# =============================================================================

_config: Config | None = None


def get_config() -> Config:
    """Get the global Config singleton.

    This function provides a lazy-loaded singleton instance of Config.
    Use this instead of importing `container.config()` to avoid circular imports.

    Returns:
        The global Config instance
    """
    global _config
    if _config is None:
        _config = Config()
    return _config
