"""Tests for config loader."""

from pathlib import Path

import pytest
import yaml

from app.core.config_loader import ConfigLoader, ConfigManager
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
                "approach": "practical",
            },
        },
        "topic_collection": {
            "region_weights": {"domestic": 0.3, "foreign": 0.7},
            "enabled_sources": ["reddit"],
        },
        "scoring": {
            "weights": {
                "source_credibility": 0.15,
                "source_score": 0.15,
                "freshness": 0.20,
                "trend_momentum": 0.10,
                "category_relevance": 0.15,
                "keyword_relevance": 0.10,
                "entity_relevance": 0.05,
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
def test_config_loader_init(config_dir):
    """Test ConfigLoader initialization."""
    loader = ConfigLoader(config_dir)
    assert loader.config_dir == config_dir


@pytest.mark.unit
def test_config_loader_default_dir():
    """Test ConfigLoader with default directory."""
    loader = ConfigLoader()
    assert loader.config_dir == Path("config/channels")


@pytest.mark.unit
def test_load_channel_config_success(config_dir, create_config_file):
    """Test loading a valid channel config."""
    create_config_file("test-channel")
    loader = ConfigLoader(config_dir)

    config = loader.load_channel_config("test-channel")

    assert config.channel.id == "test-channel"
    assert config.channel.name == "Test Channel"
    assert config.persona.name == "TestBot"


@pytest.mark.unit
def test_load_channel_config_not_found(config_dir):
    """Test loading non-existent config."""
    loader = ConfigLoader(config_dir)

    with pytest.raises(ConfigNotFoundError, match="Config file not found"):
        loader.load_channel_config("nonexistent")


@pytest.mark.unit
def test_load_channel_config_invalid_yaml(config_dir):
    """Test loading config with invalid YAML."""
    config_path = config_dir / "invalid.yaml"
    with open(config_path, "w") as f:
        f.write("invalid: yaml: content:\n  - bad indent")

    loader = ConfigLoader(config_dir)

    with pytest.raises(ConfigError, match="Invalid YAML"):
        loader.load_channel_config("invalid")


@pytest.mark.unit
def test_load_channel_config_validation_error(config_dir, valid_config_data):
    """Test loading config with validation errors."""
    invalid_data = valid_config_data.copy()
    invalid_data["channel"]["youtube"]["handle"] = "invalid_handle"

    config_path = config_dir / "invalid-validation.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(invalid_data, f)

    loader = ConfigLoader(config_dir)

    with pytest.raises(ConfigValidationError, match="Invalid configuration"):
        loader.load_channel_config("invalid-validation")


@pytest.mark.unit
def test_load_channel_config_id_mismatch(config_dir, valid_config_data):
    """Test loading config with ID mismatch."""
    config_data = valid_config_data.copy()
    config_data["channel"]["id"] = "different-id"

    config_path = config_dir / "test-channel.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    loader = ConfigLoader(config_dir)

    with pytest.raises(ConfigValidationError, match="Channel ID mismatch"):
        loader.load_channel_config("test-channel")


@pytest.mark.unit
def test_load_all_channels_success(config_dir, create_config_file, valid_config_data):
    """Test loading all channel configs."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    loader = ConfigLoader(config_dir)
    configs = loader.load_all_channels()

    assert len(configs) == 2
    assert "channel-1" in configs
    assert "channel-2" in configs


@pytest.mark.unit
def test_load_all_channels_empty_dir(config_dir):
    """Test loading from empty directory."""
    loader = ConfigLoader(config_dir)
    configs = loader.load_all_channels()

    assert configs == {}


@pytest.mark.unit
def test_load_all_channels_skip_invalid(config_dir, create_config_file):
    """Test loading all channels skips invalid configs."""
    create_config_file("valid-channel")

    # Create invalid config
    invalid_path = config_dir / "invalid.yaml"
    with open(invalid_path, "w") as f:
        f.write("invalid: yaml: :\n")

    loader = ConfigLoader(config_dir)
    configs = loader.load_all_channels()

    assert len(configs) == 1
    assert "valid-channel" in configs


@pytest.mark.unit
def test_validate_config_file_valid(config_dir, create_config_file):
    """Test validating a valid config file."""
    config_path = create_config_file("test-channel")
    loader = ConfigLoader(config_dir)

    is_valid, errors = loader.validate_config_file(config_path)

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

    loader = ConfigLoader(config_dir)
    is_valid, errors = loader.validate_config_file(config_path)

    assert is_valid is False
    assert len(errors) > 0


@pytest.mark.unit
def test_validate_config_file_not_found(config_dir):
    """Test validating non-existent file."""
    loader = ConfigLoader(config_dir)
    config_path = config_dir / "nonexistent.yaml"

    is_valid, errors = loader.validate_config_file(config_path)

    assert is_valid is False
    assert "does not exist" in errors[0]


@pytest.mark.unit
def test_config_manager_get_config(config_dir, create_config_file):
    """Test ConfigManager get_config."""
    create_config_file("test-channel")
    manager = ConfigManager(config_dir)

    config = manager.get_config("test-channel")

    assert config.channel.id == "test-channel"
    assert "test-channel" in manager._cache


@pytest.mark.unit
def test_config_manager_cache(config_dir, create_config_file):
    """Test ConfigManager caching."""
    create_config_file("test-channel")
    manager = ConfigManager(config_dir)

    # First load
    config1 = manager.get_config("test-channel")

    # Second load should use cache
    config2 = manager.get_config("test-channel")

    assert config1 is config2


@pytest.mark.unit
def test_config_manager_reload_config(config_dir, create_config_file, valid_config_data):
    """Test ConfigManager reload_config."""
    config_path = create_config_file("test-channel")
    manager = ConfigManager(config_dir)

    # Initial load
    config1 = manager.get_config("test-channel")
    assert config1.channel.name == "Test Channel"

    # Modify config file
    modified_data = valid_config_data.copy()
    modified_data["channel"]["name"] = "Modified Channel"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(modified_data, f)

    # Reload
    config2 = manager.reload_config("test-channel")

    assert config2.channel.name == "Modified Channel"


@pytest.mark.unit
def test_config_manager_reload_all(config_dir, create_config_file, valid_config_data):
    """Test ConfigManager reload_all."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    manager = ConfigManager(config_dir)

    # Initial load
    manager.get_config("channel-1")

    # Reload all
    configs = manager.reload_all()

    assert len(configs) == 2
    assert "channel-1" in configs
    assert "channel-2" in configs


@pytest.mark.unit
def test_config_manager_clear_cache(config_dir, create_config_file):
    """Test ConfigManager clear_cache."""
    create_config_file("test-channel")
    manager = ConfigManager(config_dir)

    manager.get_config("test-channel")
    assert len(manager._cache) == 1

    manager.clear_cache()
    assert len(manager._cache) == 0


@pytest.mark.unit
def test_config_manager_cached_channel_ids(config_dir, create_config_file, valid_config_data):
    """Test ConfigManager cached_channel_ids."""
    create_config_file("channel-1")

    config_2 = valid_config_data.copy()
    config_2["channel"]["id"] = "channel-2"
    create_config_file("channel-2", config_2)

    manager = ConfigManager(config_dir)

    manager.get_config("channel-1")
    manager.get_config("channel-2")

    cached_ids = manager.cached_channel_ids
    assert len(cached_ids) == 2
    assert "channel-1" in cached_ids
    assert "channel-2" in cached_ids
