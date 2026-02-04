"""Unit tests for video generation configuration models."""

import pytest
from pydantic import ValidationError

from app.config.video import (
    CompositionConfig,
    DALLEConfig,
    PixabayConfig,
    StableDiffusionConfig,
    SubtitleConfig,
    SubtitleStyleConfig,
    ThumbnailConfig,
    TTSProviderConfig,
    VideoGenerationConfig,
    VisualConfig,
    VisualSourceConfig,
)


class TestTTSProviderConfig:
    """Tests for TTSProviderConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TTSProviderConfig()
        assert config.provider == "edge-tts"
        assert config.default_voice_ko_male == "ko-KR-InJoonNeural"
        assert config.default_voice_ko_female == "ko-KR-SunHiNeural"
        assert config.default_voice_en == "en-US-AriaNeural"
        assert config.speed == 1.0
        assert config.pitch == 0
        assert config.volume == 0

    def test_provider_options(self):
        """Test provider validation."""
        config = TTSProviderConfig(provider="edge-tts")
        assert config.provider == "edge-tts"

        config = TTSProviderConfig(provider="elevenlabs")
        assert config.provider == "elevenlabs"

        with pytest.raises(ValidationError):
            TTSProviderConfig(provider="invalid")

    def test_speed_range(self):
        """Test speed validation."""
        config = TTSProviderConfig(speed=0.5)
        assert config.speed == 0.5

        config = TTSProviderConfig(speed=2.0)
        assert config.speed == 2.0

        with pytest.raises(ValidationError):
            TTSProviderConfig(speed=0.4)

        with pytest.raises(ValidationError):
            TTSProviderConfig(speed=2.1)

    def test_pitch_range(self):
        """Test pitch validation."""
        config = TTSProviderConfig(pitch=-50)
        assert config.pitch == -50

        config = TTSProviderConfig(pitch=50)
        assert config.pitch == 50

        with pytest.raises(ValidationError):
            TTSProviderConfig(pitch=-51)

        with pytest.raises(ValidationError):
            TTSProviderConfig(pitch=51)


class TestSubtitleStyleConfig:
    """Tests for SubtitleStyleConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SubtitleStyleConfig()
        assert config.font_name == "Pretendard"
        assert config.font_size == 48
        assert config.primary_color == "#FFFFFF"
        assert config.outline_color == "#000000"
        assert config.background_opacity == 0.7

    def test_font_size_range(self):
        """Test font_size validation."""
        config = SubtitleStyleConfig(font_size=12)
        assert config.font_size == 12

        config = SubtitleStyleConfig(font_size=96)
        assert config.font_size == 96

        with pytest.raises(ValidationError):
            SubtitleStyleConfig(font_size=11)

        with pytest.raises(ValidationError):
            SubtitleStyleConfig(font_size=97)


class TestSubtitleConfig:
    """Tests for SubtitleConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SubtitleConfig()
        assert config.enabled is True
        assert config.format == "ass"
        assert config.position == "bottom"
        assert config.highlight_current_word is True
        assert isinstance(config.style, SubtitleStyleConfig)

    def test_format_options(self):
        """Test format validation."""
        config = SubtitleConfig(format="ass")
        assert config.format == "ass"

        config = SubtitleConfig(format="srt")
        assert config.format == "srt"

        with pytest.raises(ValidationError):
            SubtitleConfig(format="vtt")

    def test_position_options(self):
        """Test position validation."""
        for position in ["bottom", "center", "top"]:
            config = SubtitleConfig(position=position)
            assert config.position == position

        with pytest.raises(ValidationError):
            SubtitleConfig(position="left")


class TestVisualSourceConfig:
    """Tests for VisualSourceConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VisualSourceConfig()
        assert config.api_key_env == "PEXELS_API_KEY"
        assert config.orientation == "portrait"
        assert config.min_duration == 5
        assert config.max_results == 10
        assert config.quality == "hd"

    def test_orientation_options(self):
        """Test orientation validation."""
        for orientation in ["portrait", "landscape", "square"]:
            config = VisualSourceConfig(orientation=orientation)
            assert config.orientation == orientation

        with pytest.raises(ValidationError):
            VisualSourceConfig(orientation="circular")


class TestPixabayConfig:
    """Tests for PixabayConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PixabayConfig()
        assert config.api_key_env == "PIXABAY_API_KEY"
        assert config.orientation == "portrait"
        assert config.image_type == "photo"

    def test_image_type_options(self):
        """Test image_type validation."""
        for image_type in ["all", "photo", "illustration", "vector"]:
            config = PixabayConfig(image_type=image_type)
            assert config.image_type == image_type

        with pytest.raises(ValidationError):
            PixabayConfig(image_type="gif")


class TestStableDiffusionConfig:
    """Tests for StableDiffusionConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = StableDiffusionConfig()
        assert config.service_url == "http://sd:7860"
        assert config.enabled is True
        assert config.timeout == 120.0
        assert config.base_width == 768
        assert config.base_height == 1024
        assert config.num_inference_steps == 8
        assert config.guidance_scale == 2.0

    def test_timeout_range(self):
        """Test timeout validation."""
        config = StableDiffusionConfig(timeout=10.0)
        assert config.timeout == 10.0

        config = StableDiffusionConfig(timeout=600.0)
        assert config.timeout == 600.0

        with pytest.raises(ValidationError):
            StableDiffusionConfig(timeout=9.9)

        with pytest.raises(ValidationError):
            StableDiffusionConfig(timeout=600.1)

    def test_dimension_ranges(self):
        """Test dimension validation."""
        config = StableDiffusionConfig(base_width=256, base_height=256)
        assert config.base_width == 256
        assert config.base_height == 256

        config = StableDiffusionConfig(base_width=1024, base_height=1024)
        assert config.base_width == 1024
        assert config.base_height == 1024


class TestDALLEConfig:
    """Tests for DALLEConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DALLEConfig()
        assert config.model == "dall-e-3"
        assert config.size == "1024x1792"
        assert config.quality == "standard"
        assert config.style == "natural"

    def test_quality_options(self):
        """Test quality validation."""
        config = DALLEConfig(quality="standard")
        assert config.quality == "standard"

        config = DALLEConfig(quality="hd")
        assert config.quality == "hd"

        with pytest.raises(ValidationError):
            DALLEConfig(quality="ultra")

    def test_style_options(self):
        """Test style validation."""
        config = DALLEConfig(style="vivid")
        assert config.style == "vivid"

        config = DALLEConfig(style="natural")
        assert config.style == "natural"

        with pytest.raises(ValidationError):
            DALLEConfig(style="abstract")


class TestVisualConfig:
    """Tests for VisualConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VisualConfig()
        assert len(config.source_priority) > 0
        assert config.cache_enabled is True
        assert config.cache_ttl_hours == 24
        assert isinstance(config.pexels, VisualSourceConfig)
        assert isinstance(config.pixabay, PixabayConfig)
        assert isinstance(config.stable_diffusion, StableDiffusionConfig)
        assert isinstance(config.dalle, DALLEConfig)

    def test_threshold_ranges(self):
        """Test threshold validation."""
        config = VisualConfig(
            metadata_score_threshold=0.0,
            clip_score_threshold=0.0,
            clip_img2img_threshold=0.0,
        )
        assert config.metadata_score_threshold == 0.0

        config = VisualConfig(
            metadata_score_threshold=1.0,
            clip_score_threshold=1.0,
            clip_img2img_threshold=1.0,
        )
        assert config.clip_score_threshold == 1.0


class TestCompositionConfig:
    """Tests for CompositionConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CompositionConfig()
        assert config.width == 1080
        assert config.height == 1920
        assert config.fps == 30
        assert config.video_codec == "libx264"
        assert config.crf == 23
        assert config.preset == "medium"

    def test_resolution_ranges(self):
        """Test resolution validation."""
        config = CompositionConfig(width=480, height=480)
        assert config.width == 480

        config = CompositionConfig(width=3840, height=3840)
        assert config.width == 3840

        with pytest.raises(ValidationError):
            CompositionConfig(width=479)

    def test_preset_options(self):
        """Test preset validation."""
        presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
        for preset in presets:
            config = CompositionConfig(preset=preset)
            assert config.preset == preset

        with pytest.raises(ValidationError):
            CompositionConfig(preset="invalid")


class TestThumbnailConfig:
    """Tests for ThumbnailConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ThumbnailConfig()
        assert config.width == 1080
        assert config.height == 1920
        assert config.title_font == "Noto Sans CJK KR"
        assert config.quality == 95

    def test_title_size_range(self):
        """Test title_size validation."""
        config = ThumbnailConfig(title_size=24)
        assert config.title_size == 24

        config = ThumbnailConfig(title_size=200)
        assert config.title_size == 200

        with pytest.raises(ValidationError):
            ThumbnailConfig(title_size=23)

        with pytest.raises(ValidationError):
            ThumbnailConfig(title_size=201)

    def test_text_position_options(self):
        """Test text_position validation."""
        config = ThumbnailConfig(text_position="center")
        assert config.text_position == "center"

        config = ThumbnailConfig(text_position="bottom")
        assert config.text_position == "bottom"

        with pytest.raises(ValidationError):
            ThumbnailConfig(text_position="top")


class TestVideoGenerationConfig:
    """Tests for complete VideoGenerationConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VideoGenerationConfig()
        assert isinstance(config.tts, TTSProviderConfig)
        assert isinstance(config.subtitle, SubtitleConfig)
        assert isinstance(config.visual, VisualConfig)
        assert isinstance(config.composition, CompositionConfig)
        assert isinstance(config.thumbnail, ThumbnailConfig)
        assert config.output_dir == "./outputs/videos"
        assert config.cleanup_temp is True
        assert config.max_retries == 3

    def test_custom_subconfigs(self):
        """Test custom sub-configurations."""
        config = VideoGenerationConfig(
            tts=TTSProviderConfig(provider="elevenlabs"),
            composition=CompositionConfig(fps=60),
            max_retries=5,
        )
        assert config.tts.provider == "elevenlabs"
        assert config.composition.fps == 60
        assert config.max_retries == 5

    def test_timeout_range(self):
        """Test timeout_seconds validation."""
        config = VideoGenerationConfig(timeout_seconds=60)
        assert config.timeout_seconds == 60

        config = VideoGenerationConfig(timeout_seconds=86400)
        assert config.timeout_seconds == 86400

        with pytest.raises(ValidationError):
            VideoGenerationConfig(timeout_seconds=59)

        with pytest.raises(ValidationError):
            VideoGenerationConfig(timeout_seconds=86401)
