"""Tests for visual sourcing services."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.config.video import VisualConfig
from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.manager import VisualSourcingManager


class TestVisualAsset:
    """Test suite for VisualAsset dataclass."""

    def test_is_video(self) -> None:
        """Test is_video property."""
        video_asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url="https://example.com/video.mp4",
        )
        image_asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://example.com/image.jpg",
        )

        assert video_asset.is_video is True
        assert image_asset.is_video is False

    def test_is_image(self) -> None:
        """Test is_image property."""
        video_asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url="https://example.com/video.mp4",
        )
        image_asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://example.com/image.jpg",
        )

        assert video_asset.is_image is False
        assert image_asset.is_image is True

    def test_is_downloaded(self, tmp_path: Path) -> None:
        """Test is_downloaded property."""
        asset_without_path = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://example.com/image.jpg",
        )

        image_path = tmp_path / "image.jpg"
        image_path.write_bytes(b"fake image")

        asset_with_path = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://example.com/image.jpg",
            path=image_path,
        )

        assert asset_without_path.is_downloaded is False
        assert asset_with_path.is_downloaded is True


class TestFallbackGenerator:
    """Test suite for FallbackGenerator."""

    @pytest.fixture
    def generator(self) -> FallbackGenerator:
        """Create a FallbackGenerator instance."""
        return FallbackGenerator()

    @pytest.mark.asyncio
    async def test_search_returns_assets(self, generator: FallbackGenerator) -> None:
        """Test that search returns fallback assets."""
        assets = await generator.search(query="test", max_results=2)

        assert len(assets) > 0
        for asset in assets:
            assert isinstance(asset, VisualAsset)
            assert asset.type in (
                VisualSourceType.SOLID_COLOR,
                VisualSourceType.GRADIENT,
            )

    @pytest.mark.asyncio
    async def test_download_solid_color(self, generator: FallbackGenerator, tmp_path: Path) -> None:
        """Test downloading (creating) a solid color image."""
        asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color="#FF0000",
            width=100,
            height=100,
            source="fallback",
            source_id="solid_test",
        )

        result = await generator.download(asset, tmp_path)

        assert result.path is not None
        assert result.path.exists()

    @pytest.mark.asyncio
    async def test_download_gradient(self, generator: FallbackGenerator, tmp_path: Path) -> None:
        """Test downloading (creating) a gradient image."""
        asset = VisualAsset(
            type=VisualSourceType.GRADIENT,
            gradient_colors=["#FF0000", "#0000FF"],
            width=100,
            height=100,
            source="fallback",
            source_id="gradient_test",
        )

        result = await generator.download(asset, tmp_path)

        assert result.path is not None
        assert result.path.exists()


class TestVisualSourcingManager:
    """Test suite for VisualSourcingManager."""

    @pytest.fixture
    def mock_pexels(self) -> AsyncMock:
        """Create a mock Pexels client."""
        client = AsyncMock()
        client.search_videos = AsyncMock(return_value=[])
        client.search_images = AsyncMock(return_value=[])
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_ai_generator(self) -> AsyncMock:
        """Create a mock AI image generator."""
        generator = AsyncMock()
        generator.generate = AsyncMock(return_value=[])
        generator.download = AsyncMock()
        generator.close = AsyncMock()
        return generator

    @pytest.fixture
    def mock_fallback(self) -> AsyncMock:
        """Create a mock fallback generator."""
        generator = AsyncMock()
        generator.search = AsyncMock(return_value=[])
        generator.download = AsyncMock()
        return generator

    @pytest.fixture
    def manager(
        self,
        mock_pexels: AsyncMock,
        mock_ai_generator: AsyncMock,
        mock_fallback: AsyncMock,
    ) -> VisualSourcingManager:
        """Create a VisualSourcingManager with mocked dependencies."""
        return VisualSourcingManager(
            config=VisualConfig(),
            pexels_client=mock_pexels,
            ai_generator=mock_ai_generator,
            fallback_generator=mock_fallback,
        )

    @pytest.mark.asyncio
    async def test_source_visuals_uses_priority(
        self,
        manager: VisualSourcingManager,
        mock_pexels: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test that visual sourcing follows priority order."""
        await manager.source_visuals(
            keywords=["test"],
            duration_needed=10.0,
            output_dir=tmp_path,
        )

        # Should try stock videos first (based on default priority)
        mock_pexels.search_videos.assert_called()

    @pytest.mark.asyncio
    async def test_source_visuals_uses_fallback(
        self,
        manager: VisualSourcingManager,
        mock_fallback: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test that fallback is used when other sources fail."""
        # Configure mock to return fallback asset
        fallback_asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color="#000000",
            source="fallback",
            source_id="test",
        )
        mock_fallback.search.return_value = [fallback_asset]
        mock_fallback.download.return_value = fallback_asset

        assets = await manager.source_visuals(
            keywords=["test"],
            duration_needed=10.0,
            output_dir=tmp_path,
        )

        assert len(assets) > 0 or mock_fallback.search.called


class TestVisualConfig:
    """Test visual configuration."""

    def test_default_config(self) -> None:
        """Test default visual configuration."""
        config = VisualConfig()

        assert len(config.source_priority) > 0
        assert "stock_video" in config.source_priority or "stock_image" in config.source_priority

    def test_custom_priority(self) -> None:
        """Test custom source priority."""
        config = VisualConfig(source_priority=["ai_image", "solid_color"])

        assert config.source_priority[0] == "ai_image"
        assert config.source_priority[1] == "solid_color"
