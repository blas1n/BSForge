"""Tests for app.core.config module."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.unit
def test_settings_default_values(monkeypatch):
    """Test that settings have correct default values."""
    # Remove .env file loading for this test to check actual defaults
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "BSForge"
    assert settings.app_env == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"


@pytest.mark.unit
def test_settings_is_development():
    """Test is_development property."""
    settings = Settings(app_env="development")
    assert settings.is_development is True

    settings = Settings(app_env="production")
    assert settings.is_development is False


@pytest.mark.unit
def test_settings_is_production():
    """Test is_production property."""
    settings = Settings(app_env="production")
    assert settings.is_production is True

    settings = Settings(app_env="development")
    assert settings.is_production is False


@pytest.mark.unit
def test_settings_database_url_validation():
    """Test that database URL must use asyncpg driver."""
    # Valid asyncpg URL
    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost:5432/db")
    assert "asyncpg" in str(settings.database_url)

    # Invalid URL should raise error
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://user:pass@localhost:5432/db")


@pytest.mark.unit
def test_settings_pool_size_constraints():
    """Test database pool size constraints."""
    # Valid pool size
    settings = Settings(database_pool_size=10)
    assert settings.database_pool_size == 10

    # Pool size too small
    with pytest.raises(ValidationError):
        Settings(database_pool_size=0)

    # Pool size too large
    with pytest.raises(ValidationError):
        Settings(database_pool_size=100)


@pytest.mark.unit
def test_settings_port_constraints():
    """Test API port constraints."""
    # Valid port
    settings = Settings(api_port=8000)
    assert settings.api_port == 8000

    # Invalid port (too small)
    with pytest.raises(ValidationError):
        Settings(api_port=0)

    # Invalid port (too large)
    with pytest.raises(ValidationError):
        Settings(api_port=70000)


@pytest.mark.unit
def test_settings_env_literal():
    """Test that app_env only accepts valid values."""
    # Valid values
    for env in ["development", "staging", "production"]:
        settings = Settings(app_env=env)
        assert settings.app_env == env

    # Invalid value
    with pytest.raises(ValidationError):
        Settings(app_env="invalid")


@pytest.mark.unit
def test_settings_log_level_literal():
    """Test that log_level only accepts valid values."""
    # Valid values
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        settings = Settings(log_level=level)
        assert settings.log_level == level

    # Invalid value
    with pytest.raises(ValidationError):
        Settings(log_level="INVALID")


@pytest.mark.unit
def test_settings_feature_flags():
    """Test feature flag settings."""
    settings = Settings()

    assert settings.enable_ab_testing is True
    assert settings.enable_auto_upload is False
    assert settings.enable_series_detection is True
    assert settings.enable_trend_collection is True


@pytest.mark.unit
def test_settings_from_env(monkeypatch):
    """Test loading settings from environment variables."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")

    settings = Settings()

    assert settings.app_name == "TestApp"
    assert settings.app_env == "production"
    assert settings.debug is True
