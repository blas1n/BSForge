"""Tests for app.core.config module."""

import pytest
from pydantic import ValidationError

from app.core.config import Config


@pytest.mark.unit
def test_config_default_values(monkeypatch):
    """Test that config has correct default values."""
    # Remove .env file loading for this test to check actual defaults
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    config = Config(_env_file=None)

    assert config.app_name == "BSForge"
    assert config.app_env == "development"
    assert config.debug is False
    assert config.log_level == "INFO"


@pytest.mark.unit
def test_config_is_development():
    """Test is_development property."""
    config = Config(app_env="development")
    assert config.is_development is True

    config = Config(app_env="production")
    assert config.is_development is False


@pytest.mark.unit
def test_config_is_production():
    """Test is_production property."""
    config = Config(app_env="production")
    assert config.is_production is True

    config = Config(app_env="development")
    assert config.is_production is False


@pytest.mark.unit
def test_config_database_url_validation():
    """Test that database URL must use asyncpg driver."""
    # Valid asyncpg URL
    config = Config(database_url="postgresql+asyncpg://user:pass@localhost:5432/db")
    assert "asyncpg" in str(config.database_url)

    # Invalid URL should raise error
    with pytest.raises(ValidationError):
        Config(database_url="postgresql://user:pass@localhost:5432/db")


@pytest.mark.unit
def test_config_pool_size_constraints():
    """Test database pool size constraints."""
    # Valid pool size
    config = Config(database_pool_size=10)
    assert config.database_pool_size == 10

    # Pool size too small
    with pytest.raises(ValidationError):
        Config(database_pool_size=0)

    # Pool size too large
    with pytest.raises(ValidationError):
        Config(database_pool_size=100)


@pytest.mark.unit
def test_config_port_constraints():
    """Test API port constraints."""
    # Valid port
    config = Config(api_port=8000)
    assert config.api_port == 8000

    # Invalid port (too small)
    with pytest.raises(ValidationError):
        Config(api_port=0)

    # Invalid port (too large)
    with pytest.raises(ValidationError):
        Config(api_port=70000)


@pytest.mark.unit
def test_config_env_literal():
    """Test that app_env only accepts valid values."""
    # Valid values
    for env in ["development", "staging", "production"]:
        config = Config(app_env=env)
        assert config.app_env == env

    # Invalid value
    with pytest.raises(ValidationError):
        Config(app_env="invalid")


@pytest.mark.unit
def test_config_log_level_literal():
    """Test that log_level only accepts valid values."""
    # Valid values
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        config = Config(log_level=level)
        assert config.log_level == level

    # Invalid value
    with pytest.raises(ValidationError):
        Config(log_level="INVALID")


@pytest.mark.unit
def test_config_feature_flags():
    """Test feature flag settings."""
    config = Config()

    assert config.enable_ab_testing is True
    assert config.enable_auto_upload is False
    assert config.enable_series_detection is True
    assert config.enable_trend_collection is True


@pytest.mark.unit
def test_config_from_env(monkeypatch):
    """Test loading config from environment variables."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")

    config = Config()

    assert config.app_name == "TestApp"
    assert config.app_env == "production"
    assert config.debug is True
