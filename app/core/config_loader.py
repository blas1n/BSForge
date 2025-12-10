"""Configuration loader for channel configs.

This module provides functionality to load and validate channel configuration
files from YAML.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.config import ChannelConfig
from app.core.exceptions import ConfigError, ConfigNotFoundError, ConfigValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConfigLoader:
    """YAML configuration file loader.

    This class handles loading, parsing, and validating channel configuration
    files from YAML format.

    Example:
        >>> loader = ConfigLoader()
        >>> config = loader.load_channel_config("example-tech-channel")
        >>> print(config.channel.name)
        '테크 예시 채널'
    """

    def __init__(self, config_dir: Path | str | None = None):
        """Initialize the config loader.

        Args:
            config_dir: Directory containing config files.
                       Defaults to ./config/channels/
        """
        if config_dir is None:
            config_dir = Path("config/channels")
        self.config_dir = Path(config_dir)
        logger.info("ConfigLoader initialized", config_dir=str(self.config_dir))

    def load_channel_config(self, channel_id: str) -> ChannelConfig:
        """Load and validate a channel configuration file.

        Args:
            channel_id: Channel identifier (filename without .yaml)

        Returns:
            Validated ChannelConfig object

        Raises:
            ConfigNotFoundError: If config file doesn't exist
            ConfigValidationError: If config validation fails
            ConfigError: For other configuration errors
        """
        config_path = self.config_dir / f"{channel_id}.yaml"

        if not config_path.exists():
            logger.error("Channel config not found", channel_id=channel_id, path=str(config_path))
            raise ConfigNotFoundError(f"Config file not found: {config_path}")

        try:
            logger.debug("Loading channel config", channel_id=channel_id)
            raw_config = self._load_yaml(config_path)
            config = self._validate_config(raw_config, channel_id)
            logger.info("Channel config loaded successfully", channel_id=channel_id)
            return config

        except ConfigNotFoundError:
            raise
        except ConfigValidationError:
            raise
        except Exception as e:
            logger.error(
                "Failed to load channel config",
                channel_id=channel_id,
                error=str(e),
                exc_info=True,
            )
            raise ConfigError(f"Failed to load config for {channel_id}: {e}") from e

    def load_all_channels(self) -> dict[str, ChannelConfig]:
        """Load all channel configurations from the config directory.

        Returns:
            Dictionary mapping channel IDs to ChannelConfig objects

        Raises:
            ConfigError: If loading fails
        """
        if not self.config_dir.exists():
            logger.warning("Config directory does not exist", path=str(self.config_dir))
            return {}

        configs: dict[str, ChannelConfig] = {}
        yaml_files = list(self.config_dir.glob("*.yaml"))

        logger.info("Loading all channel configs", file_count=len(yaml_files))

        for config_file in yaml_files:
            channel_id = config_file.stem
            try:
                config = self.load_channel_config(channel_id)
                configs[channel_id] = config
            except (ConfigNotFoundError, ConfigValidationError, ConfigError) as e:
                logger.warning(
                    "Skipping invalid config",
                    channel_id=channel_id,
                    error=str(e),
                )
                continue

        logger.info("Loaded all channel configs", success_count=len(configs))
        return configs

    def validate_config_file(self, config_path: Path | str) -> tuple[bool, list[str]]:
        """Validate a config file without loading it into memory.

        Args:
            config_path: Path to the config file

        Returns:
            Tuple of (is_valid, error_messages)
        """
        config_path = Path(config_path)

        if not config_path.exists():
            return False, [f"File does not exist: {config_path}"]

        try:
            raw_config = self._load_yaml(config_path)
            self._validate_config(raw_config, config_path.stem)
            return True, []
        except ConfigValidationError as e:
            return False, [str(e)]
        except Exception as e:
            return False, [f"Validation error: {e}"]

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file from disk.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML content

        Raises:
            ConfigError: If YAML parsing fails
        """
        try:
            with open(path, encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                raise ConfigError(f"Config file must contain a YAML object: {path}")

            return content

        except yaml.YAMLError as e:
            logger.error("YAML parsing failed", path=str(path), error=str(e))
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e
        except OSError as e:
            logger.error("Failed to read config file", path=str(path), error=str(e))
            raise ConfigError(f"Cannot read {path}: {e}") from e

    def _validate_config(self, raw_config: dict[str, Any], channel_id: str) -> ChannelConfig:
        """Validate raw config dict against schema.

        Args:
            raw_config: Raw configuration dictionary
            channel_id: Channel identifier for error messages

        Returns:
            Validated ChannelConfig object

        Raises:
            ConfigValidationError: If validation fails
        """
        try:
            config = ChannelConfig(**raw_config)

            # Additional validation: ensure channel.id matches filename
            if config.channel.id != channel_id:
                raise ConfigValidationError(
                    f"Channel ID mismatch: filename is '{channel_id}' "
                    f"but config has '{config.channel.id}'"
                )

            return config

        except ValidationError as e:
            error_messages = []
            for error in e.errors():
                loc = ".".join(str(loc_part) for loc_part in error["loc"])
                msg = error["msg"]
                error_messages.append(f"{loc}: {msg}")

            full_error = "\n".join(error_messages)
            logger.error(
                "Config validation failed",
                channel_id=channel_id,
                errors=error_messages,
            )
            raise ConfigValidationError(
                f"Invalid configuration for {channel_id}:\n{full_error}"
            ) from e


class ConfigManager:
    """Manages channel configurations with caching and reload support.

    This class extends ConfigLoader with caching and hot-reload capabilities.

    Example:
        >>> manager = ConfigManager()
        >>> config = manager.get_config("example-tech-channel")
        >>> manager.reload_config("example-tech-channel")
    """

    def __init__(self, config_dir: Path | str | None = None):
        """Initialize the config manager.

        Args:
            config_dir: Directory containing config files
        """
        self.loader = ConfigLoader(config_dir)
        self._cache: dict[str, ChannelConfig] = {}
        logger.info("ConfigManager initialized")

    def get_config(self, channel_id: str, use_cache: bool = True) -> ChannelConfig:
        """Get a channel configuration.

        Args:
            channel_id: Channel identifier
            use_cache: Whether to use cached config if available

        Returns:
            ChannelConfig object

        Raises:
            ConfigNotFoundError: If config file doesn't exist
            ConfigValidationError: If config validation fails
        """
        if use_cache and channel_id in self._cache:
            logger.debug("Using cached config", channel_id=channel_id)
            return self._cache[channel_id]

        config = self.loader.load_channel_config(channel_id)
        self._cache[channel_id] = config
        return config

    def reload_config(self, channel_id: str) -> ChannelConfig:
        """Reload a channel configuration from disk.

        Args:
            channel_id: Channel identifier

        Returns:
            Reloaded ChannelConfig object
        """
        logger.info("Reloading config", channel_id=channel_id)
        if channel_id in self._cache:
            del self._cache[channel_id]
        return self.get_config(channel_id, use_cache=False)

    def reload_all(self) -> dict[str, ChannelConfig]:
        """Reload all channel configurations.

        Returns:
            Dictionary of all loaded configs
        """
        logger.info("Reloading all configs")
        self._cache.clear()
        configs = self.loader.load_all_channels()
        self._cache.update(configs)
        return configs

    def get_all_configs(self, use_cache: bool = True) -> dict[str, ChannelConfig]:
        """Get all channel configurations.

        Args:
            use_cache: Whether to use cached configs

        Returns:
            Dictionary of all configs
        """
        if use_cache and self._cache:
            logger.debug("Using cached configs", count=len(self._cache))
            return self._cache.copy()

        configs = self.loader.load_all_channels()
        self._cache.update(configs)
        return configs

    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        logger.info("Clearing config cache", cached_count=len(self._cache))
        self._cache.clear()

    @property
    def cached_channel_ids(self) -> list[str]:
        """Get list of cached channel IDs.

        Returns:
            List of channel IDs in cache
        """
        return list(self._cache.keys())
