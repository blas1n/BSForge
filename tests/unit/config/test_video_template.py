"""Unit tests for video template configuration models."""

import pytest
from pydantic import ValidationError

from app.config.video_template import (
    AudioTemplateConfig,
    CaptionConfig,
    FrameLayoutConfig,
    HeadlineConfig,
    HeadlineLineConfig,
    LayoutConfig,
    SubtitleTemplateConfig,
    VideoTemplateConfig,
    VisualEffectsConfig,
    VisualPromptConfig,
)


class TestHeadlineLineConfig:
    """Tests for HeadlineLineConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HeadlineLineConfig()
        assert config.color == "#FFFFFF"
        assert config.font_size == 72
        assert config.bold is True
        assert config.outline_width == 4

    def test_font_size_range(self):
        """Test font_size validation."""
        config = HeadlineLineConfig(font_size=24)
        assert config.font_size == 24

        config = HeadlineLineConfig(font_size=144)
        assert config.font_size == 144

        with pytest.raises(ValidationError):
            HeadlineLineConfig(font_size=23)

        with pytest.raises(ValidationError):
            HeadlineLineConfig(font_size=145)

    def test_outline_width_range(self):
        """Test outline_width validation."""
        config = HeadlineLineConfig(outline_width=0)
        assert config.outline_width == 0

        config = HeadlineLineConfig(outline_width=10)
        assert config.outline_width == 10

        with pytest.raises(ValidationError):
            HeadlineLineConfig(outline_width=-1)

        with pytest.raises(ValidationError):
            HeadlineLineConfig(outline_width=11)


class TestHeadlineConfig:
    """Tests for HeadlineConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HeadlineConfig()
        assert config.enabled is True
        assert config.position_y_ratio == 0.10
        assert isinstance(config.line1, HeadlineLineConfig)
        assert isinstance(config.line2, HeadlineLineConfig)
        assert config.font_name == "Pretendard-Bold"
        assert config.shadow_enabled is True
        assert config.background_enabled is False

    def test_position_y_ratio_range(self):
        """Test position_y_ratio validation."""
        config = HeadlineConfig(position_y_ratio=0.02)
        assert config.position_y_ratio == 0.02

        config = HeadlineConfig(position_y_ratio=0.25)
        assert config.position_y_ratio == 0.25

        with pytest.raises(ValidationError):
            HeadlineConfig(position_y_ratio=0.01)

        with pytest.raises(ValidationError):
            HeadlineConfig(position_y_ratio=0.26)

    def test_line_spacing_range(self):
        """Test line_spacing validation."""
        config = HeadlineConfig(line_spacing=1.0)
        assert config.line_spacing == 1.0

        config = HeadlineConfig(line_spacing=2.0)
        assert config.line_spacing == 2.0

        with pytest.raises(ValidationError):
            HeadlineConfig(line_spacing=0.9)

        with pytest.raises(ValidationError):
            HeadlineConfig(line_spacing=2.1)


class TestCaptionConfig:
    """Tests for CaptionConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CaptionConfig()
        assert config.enabled is True
        assert config.position_y_ratio == 0.82
        assert config.font_name == "Pretendard-Bold"
        assert config.font_size == 48
        assert config.emphasis_enabled is True

    def test_position_y_ratio_range(self):
        """Test position_y_ratio validation."""
        config = CaptionConfig(position_y_ratio=0.3)
        assert config.position_y_ratio == 0.3

        config = CaptionConfig(position_y_ratio=0.95)
        assert config.position_y_ratio == 0.95

        with pytest.raises(ValidationError):
            CaptionConfig(position_y_ratio=0.29)

        with pytest.raises(ValidationError):
            CaptionConfig(position_y_ratio=0.96)

    def test_max_chars_per_line_range(self):
        """Test max_chars_per_line validation."""
        config = CaptionConfig(max_chars_per_line=5)
        assert config.max_chars_per_line == 5

        config = CaptionConfig(max_chars_per_line=30)
        assert config.max_chars_per_line == 30

        with pytest.raises(ValidationError):
            CaptionConfig(max_chars_per_line=4)

        with pytest.raises(ValidationError):
            CaptionConfig(max_chars_per_line=31)


class TestFrameLayoutConfig:
    """Tests for FrameLayoutConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = FrameLayoutConfig()
        assert config.enabled is False
        assert config.background_color == "#1a1a2e"
        assert config.content_width_ratio == 0.85
        assert config.content_height_ratio == 0.5
        assert config.content_border_enabled is True

    def test_content_ratio_ranges(self):
        """Test content ratio validation."""
        config = FrameLayoutConfig(content_width_ratio=0.5, content_height_ratio=0.3)
        assert config.content_width_ratio == 0.5
        assert config.content_height_ratio == 0.3

        config = FrameLayoutConfig(content_width_ratio=1.0, content_height_ratio=0.7)
        assert config.content_width_ratio == 1.0
        assert config.content_height_ratio == 0.7


class TestLayoutConfig:
    """Tests for LayoutConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LayoutConfig()
        assert config.headline is None
        assert config.caption is None
        assert config.subtitle_position == "bottom"
        assert config.subtitle_margin_ratio == 0.18
        assert config.fullscreen_image is True
        assert isinstance(config.frame, FrameLayoutConfig)

    def test_with_headline(self):
        """Test layout with headline configuration."""
        config = LayoutConfig(headline=HeadlineConfig())
        assert isinstance(config.headline, HeadlineConfig)
        assert config.headline.enabled is True

    def test_with_caption(self):
        """Test layout with caption configuration."""
        config = LayoutConfig(caption=CaptionConfig())
        assert isinstance(config.caption, CaptionConfig)
        assert config.caption.enabled is True

    def test_subtitle_position_options(self):
        """Test subtitle_position validation."""
        for position in ["top", "center", "bottom"]:
            config = LayoutConfig(subtitle_position=position)
            assert config.subtitle_position == position

        with pytest.raises(ValidationError):
            LayoutConfig(subtitle_position="left")


class TestSubtitleTemplateConfig:
    """Tests for SubtitleTemplateConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SubtitleTemplateConfig()
        assert config.font_name == "Pretendard"
        assert config.font_size == 72
        assert config.bold is True
        assert config.karaoke_enabled is True

    def test_animation_ranges(self):
        """Test animation timing validation."""
        config = SubtitleTemplateConfig(fade_in_ms=0, fade_out_ms=0)
        assert config.fade_in_ms == 0

        config = SubtitleTemplateConfig(fade_in_ms=1000, fade_out_ms=1000)
        assert config.fade_in_ms == 1000

        with pytest.raises(ValidationError):
            SubtitleTemplateConfig(fade_in_ms=-1)

        with pytest.raises(ValidationError):
            SubtitleTemplateConfig(fade_in_ms=1001)


class TestVisualEffectsConfig:
    """Tests for VisualEffectsConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VisualEffectsConfig()
        assert config.ken_burns_enabled is True
        assert config.ken_burns_zoom_speed == 0.0005
        assert config.ken_burns_start_scale == 1.15
        assert config.transition_type == "flash"
        assert config.color_grading_enabled is True

    def test_transition_type_options(self):
        """Test transition_type validation."""
        for transition in ["none", "fade", "flash", "crossfade"]:
            config = VisualEffectsConfig(transition_type=transition)
            assert config.transition_type == transition

        with pytest.raises(ValidationError):
            VisualEffectsConfig(transition_type="wipe")

    def test_color_grading_ranges(self):
        """Test color grading validation."""
        config = VisualEffectsConfig(
            brightness=-0.5,
            contrast=0.5,
            saturation=0.0,
            warmth=-0.5,
        )
        assert config.brightness == -0.5

        config = VisualEffectsConfig(
            brightness=0.5,
            contrast=2.0,
            saturation=2.0,
            warmth=0.5,
        )
        assert config.contrast == 2.0


class TestAudioTemplateConfig:
    """Tests for AudioTemplateConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AudioTemplateConfig()
        assert config.bgm_volume == 0.1
        assert config.tts_speed == 1.0
        assert config.normalize_audio is True

    def test_volume_range(self):
        """Test bgm_volume validation."""
        config = AudioTemplateConfig(bgm_volume=0.0)
        assert config.bgm_volume == 0.0

        config = AudioTemplateConfig(bgm_volume=1.0)
        assert config.bgm_volume == 1.0

        with pytest.raises(ValidationError):
            AudioTemplateConfig(bgm_volume=-0.1)

        with pytest.raises(ValidationError):
            AudioTemplateConfig(bgm_volume=1.1)


class TestVisualPromptConfig:
    """Tests for VisualPromptConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VisualPromptConfig()
        assert len(config.include_keywords) > 0
        assert len(config.exclude_keywords) > 0
        assert config.style == "realistic"

    def test_style_options(self):
        """Test style validation."""
        for style in ["realistic", "semi-realistic", "stylized", "anime"]:
            config = VisualPromptConfig(style=style)
            assert config.style == style

        with pytest.raises(ValidationError):
            VisualPromptConfig(style="abstract")

    def test_build_prompt_suffix(self):
        """Test prompt suffix generation."""
        config = VisualPromptConfig(include_keywords=["keyword1", "keyword2"])
        suffix = config.build_prompt_suffix()
        assert "keyword1" in suffix
        assert "keyword2" in suffix
        assert ", " in suffix

    def test_build_negative_prompt(self):
        """Test negative prompt generation."""
        config = VisualPromptConfig(exclude_keywords=["bad1", "bad2"])
        negative = config.build_negative_prompt()
        assert "bad1" in negative
        assert "bad2" in negative


class TestVideoTemplateConfig:
    """Tests for complete VideoTemplateConfig model."""

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = VideoTemplateConfig(name="test-template")
        assert config.name == "test-template"
        assert config.extends is None
        assert config.description == ""
        assert isinstance(config.layout, LayoutConfig)
        assert isinstance(config.subtitle, SubtitleTemplateConfig)
        assert isinstance(config.visual_effects, VisualEffectsConfig)
        assert isinstance(config.audio, AudioTemplateConfig)
        assert isinstance(config.visual_prompt, VisualPromptConfig)

    def test_with_extends(self):
        """Test configuration with inheritance."""
        config = VideoTemplateConfig(
            name="child-template",
            extends="parent-template",
            description="A child template",
        )
        assert config.name == "child-template"
        assert config.extends == "parent-template"
        assert config.description == "A child template"

    def test_full_config(self):
        """Test full configuration."""
        config = VideoTemplateConfig(
            name="full-template",
            description="Full configuration",
            layout=LayoutConfig(
                headline=HeadlineConfig(),
                caption=CaptionConfig(),
            ),
            subtitle=SubtitleTemplateConfig(font_size=80),
            visual_effects=VisualEffectsConfig(transition_type="fade"),
            audio=AudioTemplateConfig(bgm_volume=0.2),
        )
        assert config.name == "full-template"
        assert config.layout.headline is not None
        assert config.layout.caption is not None
        assert config.subtitle.font_size == 80
        assert config.visual_effects.transition_type == "fade"
        assert config.audio.bgm_volume == 0.2

    def test_missing_name_fails(self):
        """Test that missing name fails validation."""
        with pytest.raises(ValidationError):
            VideoTemplateConfig()  # type: ignore
