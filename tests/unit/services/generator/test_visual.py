"""Tests for visual sourcing services."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.generator.visual.base import VisualAsset, VisualSourceType
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
    def mock_wan_video(self) -> AsyncMock:
        """Create a mock Wan video source."""
        client = AsyncMock()
        client.generate = AsyncMock(return_value=[])
        client.is_available = AsyncMock(return_value=False)
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def http_client(self) -> AsyncMock:
        """Create mock HTTP client."""
        return AsyncMock()

    @pytest.fixture
    def visual_config(self) -> AsyncMock:
        """Create mock visual config."""
        config = AsyncMock()
        config.source_priority = ["pexels_image", "pexels_video", "wan_video"]
        config.metadata_score_threshold = 0.3
        config.reuse_previous_visual_types = ["cta"]
        return config

    @pytest.fixture
    def manager(
        self,
        http_client: AsyncMock,
        visual_config: AsyncMock,
        mock_pexels: AsyncMock,
        mock_wan_video: AsyncMock,
    ) -> VisualSourcingManager:
        """Create a VisualSourcingManager with mocked dependencies."""
        return VisualSourcingManager(
            http_client=http_client,
            config=visual_config,
            pexels_client=mock_pexels,
            wan_video_source=mock_wan_video,
        )

    @pytest.mark.asyncio
    async def test_close_closes_pexels(
        self,
        manager: VisualSourcingManager,
        mock_pexels: AsyncMock,
    ) -> None:
        """Test that close() closes pexels client."""
        await manager.close()
        mock_pexels.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_fallback(
        self,
        manager: VisualSourcingManager,
        tmp_path: Path,
    ) -> None:
        """Test fallback visual creation."""
        asset = await manager._create_fallback(tmp_path, 5.0, "portrait")
        assert asset is not None
        assert asset.source == "fallback"
        assert asset.duration == 5.0
