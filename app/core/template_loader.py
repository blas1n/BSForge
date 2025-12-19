"""Video template loader with inheritance support.

This module provides a loader for video style templates that supports:
- YAML-based configuration files
- Template inheritance via 'extends' field
- Deep merging of nested configurations
- Caching for performance

Example:
    ```python
    loader = VideoTemplateLoader()
    template = loader.load("korean_shorts_standard")
    print(template.layout.headline.enabled)  # True
    ```
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from app.config.video_template import VideoTemplateConfig

logger = logging.getLogger(__name__)


class TemplateNotFoundError(Exception):
    """Raised when a template file is not found."""

    pass


class TemplateInheritanceCycleError(Exception):
    """Raised when circular inheritance is detected."""

    pass


class VideoTemplateLoader:
    """Loader for video style templates with inheritance support.

    Templates are loaded from YAML files and can inherit from other templates
    using the 'extends' field. Child template values override parent values.

    Attributes:
        templates_dir: Directory containing template YAML files
    """

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        """Initialize the template loader.

        Args:
            templates_dir: Directory containing template YAML files.
                          Defaults to 'config/templates' relative to project root.
        """
        if templates_dir is None:
            # Default to project root / config / templates
            self.templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        else:
            self.templates_dir = Path(templates_dir)

        self._cache: dict[str, VideoTemplateConfig] = {}
        self._loading: set[str] = set()  # Track currently loading templates for cycle detection

    def load(self, name: str) -> VideoTemplateConfig:
        """Load a template by name.

        Handles inheritance by loading parent templates first and merging.

        Args:
            name: Template name (without .yaml extension)

        Returns:
            Fully resolved VideoTemplateConfig

        Raises:
            TemplateNotFoundError: If template file doesn't exist
            TemplateInheritanceCycleError: If circular inheritance detected
        """
        # Return cached if available
        if name in self._cache:
            return self._cache[name]

        # Detect inheritance cycles
        if name in self._loading:
            cycle = " -> ".join(self._loading) + f" -> {name}"
            raise TemplateInheritanceCycleError(f"Circular inheritance detected: {cycle}")

        self._loading.add(name)

        try:
            raw = self._load_yaml(name)

            # Handle inheritance
            if extends := raw.get("extends"):
                logger.debug(f"Template '{name}' extends '{extends}'")
                base = self.load(extends)
                base_dict = base.model_dump()
                raw = self._deep_merge(base_dict, raw)

            config = VideoTemplateConfig(**raw)
            self._cache[name] = config

            logger.info(f"Loaded template: {name}")
            return config

        finally:
            self._loading.discard(name)

    def _load_yaml(self, name: str) -> dict[str, Any]:
        """Load raw YAML content from file.

        Args:
            name: Template name

        Returns:
            Raw dictionary from YAML

        Raises:
            TemplateNotFoundError: If file doesn't exist
        """
        path = self.templates_dir / f"{name}.yaml"

        if not path.exists():
            raise TemplateNotFoundError(f"Template not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            data = {}

        return dict(data)

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Override values take precedence. Nested dicts are merged recursively.

        Args:
            base: Base dictionary
            override: Dictionary with values to override

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def list_templates(self) -> list[str]:
        """List all available template names.

        Returns:
            List of template names (without .yaml extension)
        """
        if not self.templates_dir.exists():
            return []

        return sorted([p.stem for p in self.templates_dir.glob("*.yaml")])

    def reload(self, name: str | None = None) -> None:
        """Clear cache and optionally reload a specific template.

        Args:
            name: Template name to reload, or None to clear all cache
        """
        if name is None:
            self._cache.clear()
            logger.info("Cleared all template cache")
        else:
            self._cache.pop(name, None)
            logger.info(f"Cleared cache for template: {name}")


# Module-level singleton instance
_loader: VideoTemplateLoader | None = None


def get_template_loader() -> VideoTemplateLoader:
    """Get the singleton template loader instance.

    Returns:
        VideoTemplateLoader instance
    """
    global _loader
    if _loader is None:
        _loader = VideoTemplateLoader()
    return _loader


def load_template(name: str) -> VideoTemplateConfig:
    """Convenience function to load a template.

    Args:
        name: Template name

    Returns:
        VideoTemplateConfig
    """
    return get_template_loader().load(name)
