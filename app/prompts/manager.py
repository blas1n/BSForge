"""Prompt template manager.

Loads and renders prompts from YAML files with Mako templating.
"""

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from mako.template import Template
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class PromptType(str, Enum):
    """Available prompt types."""

    TRANSLATION = "translation"
    CLASSIFICATION = "classification"
    CONTENT_CLASSIFICATION = "content_classification"
    SCRIPT_GENERATION = "script_generation"


class PromptTemplate(BaseModel):
    """Prompt template metadata."""

    name: str
    version: str
    description: str
    template: str
    example_variables: dict[str, Any] = {}

    class Config:
        """Pydantic config."""

        frozen = True


class PromptManager:
    """Manages prompt templates with Mako rendering.

    Usage:
        >>> manager = PromptManager()
        >>> prompt = manager.render(
        ...     PromptType.TRANSLATION,
        ...     source_name="English",
        ...     target_name="Korean",
        ...     text="Hello World"
        ... )
    """

    def __init__(self, prompts_dir: Path | None = None):
        """Initialize prompt manager.

        Args:
            prompts_dir: Directory containing prompt YAML files
                        (defaults to app/prompts/templates/)
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "templates"

        self.prompts_dir = prompts_dir
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # Cache loaded templates
        self._cache: dict[PromptType, PromptTemplate] = {}

        logger.info("PromptManager initialized", prompts_dir=str(self.prompts_dir))

    def load(self, prompt_type: PromptType) -> PromptTemplate:
        """Load prompt template from YAML file.

        Args:
            prompt_type: Type of prompt to load

        Returns:
            PromptTemplate instance

        Raises:
            FileNotFoundError: If prompt file doesn't exist
            ValueError: If YAML is invalid
        """
        # Check cache
        if prompt_type in self._cache:
            return self._cache[prompt_type]

        yaml_file = self.prompts_dir / f"{prompt_type.value}.yaml"

        if not yaml_file.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {yaml_file}\n"
                f"Expected location: {self.prompts_dir}/{prompt_type.value}.yaml"
            )

        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            template = PromptTemplate(
                name=data["name"],
                version=data["version"],
                description=data["description"],
                template=data["template"],
                example_variables=data.get("example_variables", {}),
            )

            # Cache it
            self._cache[prompt_type] = template

            logger.debug(
                "Loaded prompt template",
                type=prompt_type.value,
                version=template.version,
            )

            return template

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {yaml_file}: {e}") from e
        except KeyError as e:
            raise ValueError(f"Missing required field in {yaml_file}: {e}") from e

    def render(self, prompt_type: PromptType, **variables: Any) -> str:
        """Render prompt template with variables.

        Args:
            prompt_type: Type of prompt to render
            **variables: Variables to inject into template

        Returns:
            Rendered prompt string

        Raises:
            FileNotFoundError: If prompt template doesn't exist
            ValueError: If template rendering fails
        """
        template_obj = self.load(prompt_type)

        try:
            # Create Mako template and render
            mako_template = Template(template_obj.template)
            rendered = mako_template.render(**variables)

            logger.debug(
                "Rendered prompt",
                type=prompt_type.value,
                variables=list(variables.keys()),
            )

            return str(rendered).strip()  # Explicit cast to str

        except Exception as e:
            raise ValueError(f"Failed to render {prompt_type.value} template: {e}") from e

    def clear_cache(self) -> None:
        """Clear template cache.

        Useful for reloading templates after modification.
        """
        self._cache.clear()
        logger.debug("Cleared prompt cache")


# Singleton instance
_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """Get singleton PromptManager instance.

    Returns:
        PromptManager instance
    """
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


__all__ = ["PromptManager", "PromptTemplate", "PromptType", "get_prompt_manager"]
