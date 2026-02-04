"""Unit tests for visual base module."""

from pathlib import Path

import pytest

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)


class TestVisualSourceType:
    """Tests for VisualSourceType enum."""

    def test_enum_values(self):
        """Test all enum values exist."""
        assert VisualSourceType.STOCK_VIDEO.value == "stock_video"
        assert VisualSourceType.STOCK_IMAGE.value == "stock_image"
        assert VisualSourceType.AI_IMAGE.value == "ai_image"
        assert VisualSourceType.SOLID_COLOR.value == "solid_color"
        assert VisualSourceType.GRADIENT.value == "gradient"

    def test_enum_count(self):
        """Test expected number of enum values."""
        assert len(VisualSourceType) == 5

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(VisualSourceType.STOCK_VIDEO, str)
        assert VisualSourceType.STOCK_VIDEO == "stock_video"


class TestVisualAsset:
    """Tests for VisualAsset dataclass."""

    def test_minimal_asset(self):
        """Test creating asset with only required field."""
        asset = VisualAsset(type=VisualSourceType.STOCK_IMAGE)

        assert asset.type == VisualSourceType.STOCK_IMAGE
        assert asset.path is None
        assert asset.url is None
        assert asset.duration is None
        assert asset.keywords == []
        assert asset.metadata == {}

    def test_full_asset(self):
        """Test creating asset with all fields."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            path=Path("/tmp/video.mp4"),
            url="https://example.com/video.mp4",
            duration=10.5,
            width=1080,
            height=1920,
            source="pexels",
            source_id="12345",
            license="Pexels License",
            keywords=["nature", "forest"],
            metadata={"author": "John Doe"},
            metadata_score=0.85,
        )

        assert asset.path == Path("/tmp/video.mp4")
        assert asset.url == "https://example.com/video.mp4"
        assert asset.duration == 10.5
        assert asset.width == 1080
        assert asset.height == 1920
        assert asset.source == "pexels"
        assert asset.source_id == "12345"
        assert asset.license == "Pexels License"
        assert asset.keywords == ["nature", "forest"]
        assert asset.metadata == {"author": "John Doe"}
        assert asset.metadata_score == 0.85


class TestVisualAssetIsVideo:
    """Tests for VisualAsset.is_video property."""

    def test_stock_video_is_video(self):
        """Test that STOCK_VIDEO is identified as video."""
        asset = VisualAsset(type=VisualSourceType.STOCK_VIDEO)

        assert asset.is_video is True

    def test_stock_image_is_not_video(self):
        """Test that STOCK_IMAGE is not video."""
        asset = VisualAsset(type=VisualSourceType.STOCK_IMAGE)

        assert asset.is_video is False

    def test_ai_image_is_not_video(self):
        """Test that AI_IMAGE is not video."""
        asset = VisualAsset(type=VisualSourceType.AI_IMAGE)

        assert asset.is_video is False

    def test_solid_color_is_not_video(self):
        """Test that SOLID_COLOR is not video."""
        asset = VisualAsset(type=VisualSourceType.SOLID_COLOR)

        assert asset.is_video is False

    def test_gradient_is_not_video(self):
        """Test that GRADIENT is not video."""
        asset = VisualAsset(type=VisualSourceType.GRADIENT)

        assert asset.is_video is False


class TestVisualAssetIsImage:
    """Tests for VisualAsset.is_image property."""

    def test_stock_video_is_not_image(self):
        """Test that STOCK_VIDEO is not image."""
        asset = VisualAsset(type=VisualSourceType.STOCK_VIDEO)

        assert asset.is_image is False

    def test_stock_image_is_image(self):
        """Test that STOCK_IMAGE is image."""
        asset = VisualAsset(type=VisualSourceType.STOCK_IMAGE)

        assert asset.is_image is True

    def test_ai_image_is_image(self):
        """Test that AI_IMAGE is image."""
        asset = VisualAsset(type=VisualSourceType.AI_IMAGE)

        assert asset.is_image is True

    def test_solid_color_is_image(self):
        """Test that SOLID_COLOR is image."""
        asset = VisualAsset(type=VisualSourceType.SOLID_COLOR)

        assert asset.is_image is True

    def test_gradient_is_image(self):
        """Test that GRADIENT is image."""
        asset = VisualAsset(type=VisualSourceType.GRADIENT)

        assert asset.is_image is True


class TestVisualAssetIsDownloaded:
    """Tests for VisualAsset.is_downloaded property."""

    def test_no_path_not_downloaded(self):
        """Test asset without path is not downloaded."""
        asset = VisualAsset(type=VisualSourceType.STOCK_IMAGE)

        assert asset.is_downloaded is False

    def test_nonexistent_path_not_downloaded(self):
        """Test asset with nonexistent path is not downloaded."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            path=Path("/nonexistent/file.jpg"),
        )

        assert asset.is_downloaded is False

    def test_existing_path_is_downloaded(self, tmp_path):
        """Test asset with existing path is downloaded."""
        file_path = tmp_path / "test.jpg"
        file_path.touch()

        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            path=file_path,
        )

        assert asset.is_downloaded is True


class TestVisualAssetSolidColor:
    """Tests for VisualAsset with SOLID_COLOR type."""

    def test_solid_color_asset(self):
        """Test creating solid color asset."""
        asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color="#1a1a2e",
            width=1080,
            height=1920,
        )

        assert asset.type == VisualSourceType.SOLID_COLOR
        assert asset.color == "#1a1a2e"
        assert asset.is_image is True


class TestVisualAssetGradient:
    """Tests for VisualAsset with GRADIENT type."""

    def test_gradient_asset(self):
        """Test creating gradient asset."""
        asset = VisualAsset(
            type=VisualSourceType.GRADIENT,
            gradient_colors=["#1a1a2e", "#16213e", "#0f3460"],
            width=1080,
            height=1920,
        )

        assert asset.type == VisualSourceType.GRADIENT
        assert asset.gradient_colors == ["#1a1a2e", "#16213e", "#0f3460"]
        assert asset.is_image is True


class TestBaseVisualSourceInterface:
    """Tests for BaseVisualSource abstract base class."""

    def test_cannot_instantiate(self):
        """Test that BaseVisualSource cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseVisualSource()

    def test_requires_search_method(self):
        """Test that subclass must implement search method."""

        class IncompleteSource(BaseVisualSource):
            async def download(self, asset, output_dir):
                pass

        with pytest.raises(TypeError):
            IncompleteSource()

    def test_requires_download_method(self):
        """Test that subclass must implement download method."""

        class IncompleteSource(BaseVisualSource):
            async def search(
                self, query, max_results=10, orientation="portrait", min_duration=None
            ):
                return []

        with pytest.raises(TypeError):
            IncompleteSource()

    def test_complete_implementation(self):
        """Test that complete implementation can be instantiated."""

        class CompleteSource(BaseVisualSource):
            async def search(
                self, query, max_results=10, orientation="portrait", min_duration=None
            ):
                return []

            async def download(self, asset, output_dir):
                return asset

        source = CompleteSource()
        assert isinstance(source, BaseVisualSource)
