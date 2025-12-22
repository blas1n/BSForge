"""Tests for ThumbnailGenerator."""

from pathlib import Path

import pytest

from app.config.video import ThumbnailConfig
from app.services.generator.thumbnail import ThumbnailGenerator
from app.services.generator.visual.base import VisualAsset, VisualSourceType


class TestThumbnailGenerator:
    """Test suite for ThumbnailGenerator."""

    @pytest.fixture
    def generator(self, thumbnail_config: ThumbnailConfig) -> ThumbnailGenerator:
        """Create a ThumbnailGenerator instance."""
        return ThumbnailGenerator(config=thumbnail_config)

    @pytest.mark.asyncio
    async def test_generate_with_solid_background(
        self, generator: ThumbnailGenerator, tmp_path: Path
    ) -> None:
        """Test generating thumbnail with solid background."""
        output_path = tmp_path / "thumbnail"

        result = await generator.generate(
            title="Test Video Title",
            output_path=output_path,
            background_color="#1a1a2e",
        )

        assert result.exists()
        assert result.suffix == ".jpg"

    @pytest.mark.asyncio
    async def test_generate_with_image_background(
        self, generator: ThumbnailGenerator, tmp_path: Path
    ) -> None:
        """Test generating thumbnail with image background."""
        # Create a simple test image
        from PIL import Image

        bg_path = tmp_path / "background.jpg"
        img = Image.new("RGB", (1920, 1080), color="blue")
        img.save(bg_path, "JPEG")

        background = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            path=bg_path,
            width=1920,
            height=1080,
        )

        output_path = tmp_path / "thumbnail"

        result = await generator.generate(
            title="Test Video Title",
            output_path=output_path,
            background=background,
        )

        assert result.exists()
        assert result.suffix == ".jpg"

    @pytest.mark.asyncio
    async def test_generate_creates_output_directory(
        self, generator: ThumbnailGenerator, tmp_path: Path
    ) -> None:
        """Test that generate creates output directory if needed."""
        output_path = tmp_path / "nested" / "dir" / "thumbnail"

        result = await generator.generate(
            title="Test",
            output_path=output_path,
        )

        assert result.parent.exists()


class TestTextWrapping:
    """Test text wrapping functionality."""

    @pytest.fixture
    def generator(self) -> ThumbnailGenerator:
        """Create a ThumbnailGenerator."""
        return ThumbnailGenerator()

    @pytest.fixture
    def config(self) -> ThumbnailConfig:
        """Create a ThumbnailConfig."""
        return ThumbnailConfig()

    def test_wrap_long_title(self, generator: ThumbnailGenerator, config: ThumbnailConfig) -> None:
        """Test that long titles are wrapped."""
        from PIL import ImageFont

        font = ImageFont.load_default()
        long_title = "This is a very long title that should definitely be wrapped " * 2

        wrapped = generator._wrap_text(long_title, font, max_width=500, config=config)

        assert "\n" in wrapped

    def test_short_title_not_wrapped(
        self, generator: ThumbnailGenerator, config: ThumbnailConfig
    ) -> None:
        """Test that short titles are not wrapped."""
        from PIL import ImageFont

        font = ImageFont.load_default()
        short_title = "Short"

        wrapped = generator._wrap_text(short_title, font, max_width=500, config=config)

        assert "\n" not in wrapped


class TestColorConversion:
    """Test color conversion utilities."""

    @pytest.fixture
    def generator(self) -> ThumbnailGenerator:
        """Create a ThumbnailGenerator."""
        return ThumbnailGenerator()

    def test_hex_to_rgb_white(self, generator: ThumbnailGenerator) -> None:
        """Test converting white hex to RGB."""
        rgb = generator._hex_to_rgb("#FFFFFF")
        assert rgb == (255, 255, 255)

    def test_hex_to_rgb_black(self, generator: ThumbnailGenerator) -> None:
        """Test converting black hex to RGB."""
        rgb = generator._hex_to_rgb("#000000")
        assert rgb == (0, 0, 0)

    def test_hex_to_rgb_red(self, generator: ThumbnailGenerator) -> None:
        """Test converting red hex to RGB."""
        rgb = generator._hex_to_rgb("#FF0000")
        assert rgb == (255, 0, 0)

    def test_hex_to_rgb_without_hash(self, generator: ThumbnailGenerator) -> None:
        """Test converting hex without # prefix."""
        rgb = generator._hex_to_rgb("00FF00")
        assert rgb == (0, 255, 0)


class TestThumbnailConfig:
    """Test thumbnail configuration."""

    def test_default_config(self) -> None:
        """Test default thumbnail configuration.

        Note: Defaults are optimized for YouTube Shorts (1080x1920 portrait).
        """
        config = ThumbnailConfig()

        # YouTube Shorts default dimensions
        assert config.width == 1080
        assert config.height == 1920
        assert config.quality >= 80
        assert config.quality <= 100

    def test_custom_dimensions(self) -> None:
        """Test custom thumbnail dimensions."""
        config = ThumbnailConfig(width=1920, height=1080)

        assert config.width == 1920
        assert config.height == 1080
