"""Unit tests for PromptManager."""

import pytest
from pydantic import ValidationError

from app.prompts.manager import (
    PromptManager,
    PromptTemplate,
    PromptType,
    get_prompt_manager,
)


class TestPromptManager:
    """Test PromptManager functionality."""

    def test_load_translation_prompt(self):
        """Should load translation prompt template."""
        manager = PromptManager()
        template = manager.load(PromptType.TRANSLATION)

        assert isinstance(template, PromptTemplate)
        assert template.name == "Translation Prompt"
        assert template.version == "1.0.0"
        assert "${source_name}" in template.template
        assert "${target_name}" in template.template
        assert "${text}" in template.template

    def test_load_classification_prompt(self):
        """Should load classification prompt template."""
        manager = PromptManager()
        template = manager.load(PromptType.CLASSIFICATION)

        assert isinstance(template, PromptTemplate)
        assert template.name == "Classification Prompt"
        assert template.version == "1.0.0"
        assert "${text_to_analyze}" in template.template

    def test_render_translation_prompt(self):
        """Should render translation prompt with variables."""
        manager = PromptManager()
        rendered = manager.render(
            PromptType.TRANSLATION,
            source_name="English",
            target_name="Korean",
            text="Hello World",
        )

        assert "English" in rendered
        assert "Korean" in rendered
        assert "Hello World" in rendered
        assert "${" not in rendered  # No unrendered variables
        assert "Translate the following" in rendered

    def test_render_classification_prompt(self):
        """Should render classification prompt with variables."""
        manager = PromptManager()
        rendered = manager.render(
            PromptType.CLASSIFICATION,
            text_to_analyze="OpenAI releases GPT-4.5",
        )

        assert "OpenAI releases GPT-4.5" in rendered
        assert "${" not in rendered
        assert "categories" in rendered
        assert "keywords" in rendered
        assert "entities" in rendered

    def test_cache_templates(self):
        """Should cache loaded templates."""
        manager = PromptManager()

        # First load
        template1 = manager.load(PromptType.TRANSLATION)
        # Second load (should use cache)
        template2 = manager.load(PromptType.TRANSLATION)

        assert template1 is template2  # Same object

    def test_clear_cache(self):
        """Should clear template cache."""
        manager = PromptManager()

        # Load and cache
        manager.load(PromptType.TRANSLATION)
        assert len(manager._cache) == 1

        # Clear cache
        manager.clear_cache()
        assert len(manager._cache) == 0

    def test_missing_prompt_file(self, tmp_path):
        """Should raise FileNotFoundError for missing prompt."""
        # Use tmp_path but don't create any YAML files
        manager = PromptManager(prompts_dir=tmp_path)

        with pytest.raises(FileNotFoundError) as exc_info:
            manager.load(PromptType.TRANSLATION)

        assert "not found" in str(exc_info.value).lower()

    def test_singleton_instance(self):
        """Should return same instance via get_prompt_manager."""
        manager1 = get_prompt_manager()
        manager2 = get_prompt_manager()

        assert manager1 is manager2

    def test_example_variables(self):
        """Should include example variables in template."""
        manager = PromptManager()
        template = manager.load(PromptType.TRANSLATION)

        assert template.example_variables
        assert "source_name" in template.example_variables
        assert "target_name" in template.example_variables
        assert "text" in template.example_variables

    def test_template_immutability(self):
        """Should prevent template modification."""
        manager = PromptManager()
        template = manager.load(PromptType.TRANSLATION)

        with pytest.raises(ValidationError):
            template.name = "Modified"


class TestPromptTemplate:
    """Test PromptTemplate model."""

    def test_create_template(self):
        """Should create PromptTemplate instance."""
        template = PromptTemplate(
            name="Test Prompt",
            version="1.0.0",
            description="Test description",
            template="Hello {{ name }}",
            example_variables={"name": "World"},
        )

        assert template.name == "Test Prompt"
        assert template.version == "1.0.0"
        assert template.description == "Test description"
        assert template.template == "Hello {{ name }}"
        assert template.example_variables == {"name": "World"}

    def test_default_example_variables(self):
        """Should use empty dict as default for example_variables."""
        template = PromptTemplate(
            name="Test",
            version="1.0.0",
            description="Test",
            template="Test",
        )

        assert template.example_variables == {}

    def test_template_frozen(self):
        """Should be immutable (frozen)."""
        template = PromptTemplate(
            name="Test",
            version="1.0.0",
            description="Test",
            template="Test",
        )

        with pytest.raises(ValidationError):
            template.name = "Modified"
