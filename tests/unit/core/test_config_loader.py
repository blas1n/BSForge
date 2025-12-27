"""Tests for config loader."""

from pathlib import Path

import pytest
import yaml

from app.core.config_loader import ConfigService
from app.core.exceptions import ConfigError, ConfigNotFoundError, ConfigValidationError


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory with test configs.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        Path to config directory
    """
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def valid_config_data():
    """Get valid config data.

    Returns:
        Valid configuration dictionary
    """
    return {
        "channel": {
            "id": "test-channel",
            "name": "Test Channel",
            "description": "A test channel",
            "youtube": {"channel_id": "UC_TEST", "handle": "@test"},
        },
        "persona": {
            "name": "TestBot",
            "tagline": "Testing",
            "voice": {
                "gender": "male",
                "service": "edge-tts",
                "voice_id": "test-voice",
            },
            "communication": {
                "tone": "friendly",
                "formality": "casual",
            },
            "perspective": {
                "core_values": ["실용성"],
            },
        },
        "topic_collection": {
            "global_sources": ["hackernews"],
            "scoped_sources": ["reddit"],
            "target_language": "ko",
        },
        "scoring": {
            "weights": {
                "source_credibility": 0.15,
                "source_score": 0.15,
                "freshness": 0.20,
                "trend_momentum": 0.10,
                "term_relevance": 0.20,
                "entity_relevance": 0.10,
                "novelty": 0.10,
            },
        },
        "content": {
            "target_duration": 55,
            "visual": {"source_priority": ["stock_video"], "fallback_color": "#1a1a2e"},
        },
        "upload": {
            "daily_target": 2,
            "max_daily": 3,
            "schedule": {"allowed_hours": [7, 8, 9], "min_interval_hours": 6},
        },
    }


@pytest.fixture
def create_config_file(config_dir, valid_config_data):
    """Factory to create config files.

    Args:
        config_dir: Config directory path
        valid_config_data: Valid config data

    Returns:
        Function to create config files
    """

    def _create(channel_id: str, config_data: dict | None = None):
        if config_data is None:
            config_data = valid_config_data.copy()
            config_data["channel"]["id"] = channel_id

        config_path = config_dir / f"{channel_id}.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)
        return config_path

    return _create


@pytest.mark.unit
def test_config_service_init(config_dir):
    """Test ConfigService initialization."""
    service = ConfigService(config_dir)
    assert service.config_dir == config_dir


@pytest.mark.unit
def test_config_service_default_dir():
    """Test ConfigService with default directory."""
    service = ConfigService()
    assert service.config_dir == Path("config/channels")


@pytest.mark.unit
def test_get_channel_config_success(config_dir, create_config_file):
    """Test loading a valid channel config."""
    create_config_file("test-channel")
    service = ConfigService(config_dir)

    config = service.get("test-channel")

    assert config.channel.id == "test-channel"
    assert config.channel.name == "Test Channel"
    assert config.persona.name == "TestBot"


@pytest.mark.unit
def test_get_channel_config_not_found(config_dir):
    """Test loading non-existent config."""
    service = ConfigService(config_dir)

    with pytest.raises(ConfigNotFoundError, match="Config file not found"):
        service.get("nonexistent")


@pytest.mark.unit
def test_get_channel_config_invalid_yaml(config_dir):
    """Test loading config with invalid YAML."""
    config_path = config_dir / "invalid.yaml"
    with open(config_path, "w") as f:
        f.write("invalid: yaml: content:\n  - bad indent")

    service = ConfigService(config_dir)

    with pytest.raises(ConfigError, match="Invalid YAML"):
        service.get("invalid")


@pytest.mark.unit
def test_get_channel_config_validation_error(config_dir, valid_config_data):
    """Test loading config with validation errors."""
    invalid_data = valid_config_data.copy()
    invalid_data["channel"]["youtube"]["handle"] = "invalid_handle"

    config_path = config_dir / "invalid-validation.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(invalid_data, f)

    service = ConfigService(config_dir)

    with pytest.raises(ConfigValidationError, match="Invalid configuration"):
        service.get("invalid-validation")


@pytest.mark.unit
def test_get_channel_config_id_mismatch(config_dir, valid_config_data):
    """Test loading config with ID mismatch."""
    config_data = valid_config_data.copy()
    config_data["channel"]["id"] = "different-id"

    config_path = config_dir / "test-channel.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    service = ConfigService(config_dir)

    with pytest.raises(ConfigValidationError, match="Channel ID mismatch"):
        service.get("test-channel")


@pytest.mark.unit
def test_get_all_channels_success(config_dir, create_config_file, valid_config_data):
    """Test loading all channel configs."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    service = ConfigService(config_dir)
    configs = service.get_all()

    assert len(configs) == 2
    assert "channel-1" in configs
    assert "channel-2" in configs


@pytest.mark.unit
def test_get_all_channels_empty_dir(config_dir):
    """Test loading from empty directory."""
    service = ConfigService(config_dir)
    configs = service.get_all()

    assert configs == {}


@pytest.mark.unit
def test_get_all_channels_skip_invalid(config_dir, create_config_file):
    """Test loading all channels skips invalid configs."""
    create_config_file("valid-channel")

    # Create invalid config
    invalid_path = config_dir / "invalid.yaml"
    with open(invalid_path, "w") as f:
        f.write("invalid: yaml: :\n")

    service = ConfigService(config_dir)
    configs = service.get_all()

    assert len(configs) == 1
    assert "valid-channel" in configs


@pytest.mark.unit
def test_validate_config_file_valid(config_dir, create_config_file):
    """Test validating a valid config file."""
    config_path = create_config_file("test-channel")
    service = ConfigService(config_dir)

    is_valid, errors = service.validate(config_path)

    assert is_valid is True
    assert errors == []


@pytest.mark.unit
def test_validate_config_file_invalid(config_dir, valid_config_data):
    """Test validating an invalid config file."""
    invalid_data = valid_config_data.copy()
    invalid_data["channel"]["youtube"]["handle"] = "invalid"

    config_path = config_dir / "invalid.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(invalid_data, f)

    service = ConfigService(config_dir)
    is_valid, errors = service.validate(config_path)

    assert is_valid is False
    assert len(errors) > 0


@pytest.mark.unit
def test_validate_config_file_not_found(config_dir):
    """Test validating non-existent file."""
    service = ConfigService(config_dir)
    config_path = config_dir / "nonexistent.yaml"

    is_valid, errors = service.validate(config_path)

    assert is_valid is False
    assert "does not exist" in errors[0]


@pytest.mark.unit
def test_config_service_get_with_cache(config_dir, create_config_file):
    """Test ConfigService get with caching."""
    create_config_file("test-channel")
    service = ConfigService(config_dir)

    config = service.get("test-channel")

    assert config.channel.id == "test-channel"
    assert "test-channel" in service._cache


@pytest.mark.unit
def test_config_service_cache(config_dir, create_config_file):
    """Test ConfigService caching."""
    create_config_file("test-channel")
    service = ConfigService(config_dir)

    # First load
    config1 = service.get("test-channel")

    # Second load should use cache
    config2 = service.get("test-channel")

    assert config1 is config2


@pytest.mark.unit
def test_config_service_reload(config_dir, create_config_file, valid_config_data):
    """Test ConfigService reload."""
    config_path = create_config_file("test-channel")
    service = ConfigService(config_dir)

    # Initial load
    config1 = service.get("test-channel")
    assert config1.channel.name == "Test Channel"

    # Modify config file
    modified_data = valid_config_data.copy()
    modified_data["channel"]["name"] = "Modified Channel"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(modified_data, f)

    # Reload
    config2 = service.reload("test-channel")

    assert config2.channel.name == "Modified Channel"


@pytest.mark.unit
def test_config_service_reload_all(config_dir, create_config_file, valid_config_data):
    """Test ConfigService reload_all."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    service = ConfigService(config_dir)

    # Initial load
    service.get("channel-1")

    # Reload all
    configs = service.reload_all()

    assert len(configs) == 2
    assert "channel-1" in configs
    assert "channel-2" in configs


@pytest.mark.unit
def test_config_service_clear_cache(config_dir, create_config_file):
    """Test ConfigService clear_cache."""
    create_config_file("test-channel")
    service = ConfigService(config_dir)

    service.get("test-channel")
    assert len(service._cache) == 1

    service.clear_cache()
    assert len(service._cache) == 0


@pytest.mark.unit
def test_config_service_cached_channel_ids(config_dir, create_config_file, valid_config_data):
    """Test ConfigService cached_channel_ids."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    service = ConfigService(config_dir)

    service.get("channel-1")
    service.get("channel-2")

    cached_ids = service.cached_channel_ids
    assert len(cached_ids) == 2
    assert "channel-1" in cached_ids
    assert "channel-2" in cached_ids
