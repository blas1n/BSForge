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

    assert config.enable_auto_upload is False


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


@pytest.mark.unit
def test_production_warns_empty_api_key():
    """Production with empty LLM API key emits warning."""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        Config(app_env="production", llm_api_key="", secret_key="explicit-key")
        api_warnings = [x for x in w if "LLM_API_KEY" in str(x.message)]
        assert len(api_warnings) == 1


@pytest.mark.unit
def test_production_no_warning_with_api_key():
    """Production with LLM API key set does not warn."""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        Config(app_env="production", llm_api_key="sk-test-key", secret_key="explicit-key")
        api_warnings = [x for x in w if "LLM_API_KEY" in str(x.message)]
        assert len(api_warnings) == 0


@pytest.mark.unit
def test_auto_secret_key_prefix_stripped():
    """Auto-generated secret key has 'auto:' prefix stripped."""
    config = Config(_env_file=None)
    assert not config.secret_key.startswith("auto:")
    assert len(config.secret_key) > 20  # random token is sufficiently long
