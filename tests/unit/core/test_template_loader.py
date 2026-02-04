"""Tests for video template loader."""

import tempfile
from pathlib import Path

import pytest
import yaml

from app.config.video_template import VideoTemplateConfig
from app.core.template_loader import (
    TemplateNotFoundError,
    VideoTemplateLoader,
    get_template_loader,
    load_template,
)


class TestVideoTemplateLoader:
    """Tests for VideoTemplateLoader class."""

    def test_load_minimal_template(self) -> None:
        """Test loading minimal template from project templates."""
        loader = VideoTemplateLoader()
        template = loader.load("minimal")

        assert template.name == "minimal"
        # headline replaces title_overlay in the new design
        assert template.layout.headline is None or not template.layout.headline.enabled
        assert template.subtitle.font_name == "Pretendard"
        assert not template.visual_effects.ken_burns_enabled

    def test_load_korean_shorts_standard_template(self) -> None:
        """Test loading korean_shorts_standard template with inheritance."""
        loader = VideoTemplateLoader()
        template = loader.load("korean_shorts_standard")

        assert template.name == "korean_shorts_standard"
        # Should have headline enabled
        assert template.layout.headline is not None
        assert template.layout.headline.enabled is True
        # Should have Ken Burns enabled
        assert template.visual_effects.ken_burns_enabled is True
        # korean_shorts_standard uses Bold variant
        assert template.subtitle.font_name == "Noto Sans CJK KR Bold"
        assert template.subtitle.font_size == 100

    def test_template_inheritance(self) -> None:
        """Test that template inheritance works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)

            # Create base template
            base_yaml = {
                "name": "base",
                "description": "Base template",
                "subtitle": {
                    "font_name": "Arial",
                    "font_size": 48,
                    "primary_color": "#FFFFFF",
                },
                "visual_effects": {
                    "ken_burns_enabled": False,
                    "segment_duration": 5.0,
                },
            }
            (templates_dir / "base.yaml").write_text(yaml.dump(base_yaml))

            # Create child template that extends base
            child_yaml = {
                "name": "child",
                "extends": "base",
                "description": "Child template",
                "subtitle": {
                    "font_size": 72,  # Override
                },
                "visual_effects": {
                    "ken_burns_enabled": True,  # Override
                },
            }
            (templates_dir / "child.yaml").write_text(yaml.dump(child_yaml))

            loader = VideoTemplateLoader(templates_dir=templates_dir)
            template = loader.load("child")

            # Overridden values
            assert template.subtitle.font_size == 72
            assert template.visual_effects.ken_burns_enabled is True
            # Inherited values
            assert template.subtitle.font_name == "Arial"
            assert template.subtitle.primary_color == "#FFFFFF"
            assert template.visual_effects.segment_duration == 5.0

    def test_template_caching(self) -> None:
        """Test that templates are cached after first load."""
        loader = VideoTemplateLoader()

        # Load twice
        template1 = loader.load("minimal")
        template2 = loader.load("minimal")

        # Should be same object (cached)
        assert template1 is template2

    def test_list_templates(self) -> None:
        """Test listing available templates."""
        loader = VideoTemplateLoader()
        templates = loader.list_templates()

        assert "minimal" in templates
        assert "korean_shorts_standard" in templates
        assert len(templates) >= 2

    def test_template_not_found(self) -> None:
        """Test error when template doesn't exist."""
        loader = VideoTemplateLoader()

        with pytest.raises(TemplateNotFoundError):
            loader.load("nonexistent_template")

    def test_reload_clears_cache(self) -> None:
        """Test reloading clears template cache."""
        loader = VideoTemplateLoader()

        # Load template
        template1 = loader.load("minimal")
        assert "minimal" in loader._cache

        # Reload (clear) specific template
        loader.reload("minimal")
        assert "minimal" not in loader._cache

        # Load again - should be new object
        template2 = loader.load("minimal")
        assert template1 is not template2

    def test_reload_all_clears_all_cache(self) -> None:
        """Test reloading all clears entire cache."""
        loader = VideoTemplateLoader()

        # Load templates
        loader.load("minimal")
        loader.load("korean_shorts_standard")
        assert len(loader._cache) >= 2

        # Reload all (clear)
        loader.reload()
        assert len(loader._cache) == 0


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_template_loader_singleton(self) -> None:
        """Test that get_template_loader returns singleton."""
        loader1 = get_template_loader()
        loader2 = get_template_loader()

        assert loader1 is loader2

    def test_load_template_function(self) -> None:
        """Test load_template convenience function."""
        template = load_template("minimal")

        assert isinstance(template, VideoTemplateConfig)
        assert template.name == "minimal"


class TestVideoTemplateConfig:
    """Tests for VideoTemplateConfig validation."""

    def test_default_values(self) -> None:
        """Test that config has sensible defaults."""
        config = VideoTemplateConfig(name="test")

        assert config.name == "test"
        assert config.extends is None
        assert config.description == ""
        assert config.layout is not None
        assert config.subtitle is not None
        assert config.visual_effects is not None
        assert config.audio is not None

    def test_subtitle_defaults(self) -> None:
        """Test subtitle config defaults.

        Note: Defaults are set for Korean viral style (font_size=72, bold=True).
        """
        config = VideoTemplateConfig(name="test")

        assert config.subtitle.font_name == "Pretendard"
        assert config.subtitle.font_size == 72  # Korean viral default
        assert config.subtitle.bold is True
        assert config.subtitle.primary_color == "#FFFFFF"
        assert config.subtitle.outline_color == "#000000"
        assert config.subtitle.highlight_color == "#FFFF00"
        assert config.subtitle.karaoke_enabled is True

    def test_visual_effects_defaults(self) -> None:
        """Test visual effects config defaults.

        Note: Defaults are set for Korean viral style (ken_burns=True, flash transitions).
        """
        config = VideoTemplateConfig(name="test")

        # Korean viral defaults
        assert config.visual_effects.ken_burns_enabled is True
        assert config.visual_effects.ken_burns_zoom_speed == 0.0005
        assert config.visual_effects.transition_type == "flash"
        assert config.visual_effects.segment_duration == 2.5
        assert config.visual_effects.color_grading_enabled is True

    def test_audio_defaults(self) -> None:
        """Test audio config defaults."""
        config = VideoTemplateConfig(name="test")

        assert config.audio.bgm_volume == 0.1
        assert config.audio.tts_speed == 1.0
        assert config.audio.normalize_audio is True
