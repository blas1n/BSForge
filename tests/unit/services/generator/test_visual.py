"""Tests for visual sourcing services."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config.video import (
    PixabayConfig,
    VisualConfig,
)
from app.infrastructure.http_client import HTTPClient
from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pixabay import PixabayClient


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
    def mock_pixabay(self) -> AsyncMock:
        """Create a mock Pixabay client."""
        client = AsyncMock()
        client.search_videos = AsyncMock(return_value=[])
        client.search_images = AsyncMock(return_value=[])
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_tavily_image(self) -> AsyncMock:
        """Create a mock Tavily image client."""
        client = AsyncMock()
        client.search = AsyncMock(return_value=[])
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_fallback(self) -> AsyncMock:
        """Create a mock fallback generator."""
        generator = AsyncMock()
        generator.search = AsyncMock(return_value=[])
        generator.download = AsyncMock()
        return generator

    @pytest.fixture
    def http_client(self) -> HTTPClient:
        """Create HTTP client."""
        return HTTPClient()

    @pytest.fixture
    def mock_wan_video(self) -> AsyncMock:
        """Create a mock Wan video source."""
        client = AsyncMock()
        client.generate = AsyncMock(return_value=[])
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def manager(
        self,
        http_client: HTTPClient,
        mock_pexels: AsyncMock,
        mock_pixabay: AsyncMock,
        mock_tavily_image: AsyncMock,
        mock_wan_video: AsyncMock,
        mock_fallback: AsyncMock,
    ) -> VisualSourcingManager:
        """Create a VisualSourcingManager with mocked dependencies."""
        return VisualSourcingManager(
            http_client=http_client,
            config=VisualConfig(),
            pexels_client=mock_pexels,
            pixabay_client=mock_pixabay,
            tavily_image_client=mock_tavily_image,
            wan_video_source=mock_wan_video,
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
        assert "pexels_video" in config.source_priority or "pexels_image" in config.source_priority

    def test_custom_priority(self) -> None:
        """Test custom source priority."""
        config = VisualConfig(source_priority=["wan_video", "solid_color"])

        assert config.source_priority[0] == "wan_video"
        assert config.source_priority[1] == "solid_color"

    def test_pixabay_in_default_priority(self) -> None:
        """Test that Pixabay is included in default priority."""
        config = VisualConfig()

        assert "pixabay_video" in config.source_priority
        assert "pixabay_image" in config.source_priority

    def test_wan_video_in_default_priority(self) -> None:
        """Test that Wan video is included in default priority."""
        config = VisualConfig()

        assert "wan_video" in config.source_priority


class TestPixabayConfig:
    """Test Pixabay configuration."""

    def test_default_config(self) -> None:
        """Test default Pixabay configuration."""
        config = PixabayConfig()

        assert config.api_key_env == "PIXABAY_API_KEY"
        assert config.orientation == "portrait"
        assert config.image_type == "photo"

    def test_custom_config(self) -> None:
        """Test custom Pixabay configuration."""
        config = PixabayConfig(
            orientation="landscape",
            image_type="illustration",
            min_duration=10,
        )

        assert config.orientation == "landscape"
        assert config.image_type == "illustration"
        assert config.min_duration == 10


class TestPixabayClient:
    """Test suite for PixabayClient."""

    @pytest.fixture
    def client(self) -> PixabayClient:
        """Create a PixabayClient instance with a mock API key."""
        return PixabayClient(api_key="test_api_key")

    @pytest.fixture
    def client_no_key(self) -> PixabayClient:
        """Create a PixabayClient instance without API key."""
        with patch.dict("os.environ", {}, clear=True):
            return PixabayClient(api_key=None)

    @pytest.mark.asyncio
    async def test_search_videos_no_api_key(self, client_no_key: PixabayClient) -> None:
        """Test that search returns empty list when API key is not set."""
        assets = await client_no_key.search_videos(query="test", max_results=5)

        assert assets == []

    @pytest.mark.asyncio
    async def test_search_images_no_api_key(self, client_no_key: PixabayClient) -> None:
        """Test that image search returns empty list when API key is not set."""
        assets = await client_no_key.search_images(query="test", max_results=5)

        assert assets == []

    @pytest.mark.asyncio
    async def test_orientation_mapping(self, client: PixabayClient) -> None:
        """Test orientation parameter mapping."""
        assert client._map_orientation("portrait") == "vertical"
        assert client._map_orientation("landscape") == "horizontal"
        assert client._map_orientation("square") == "all"

    def test_select_best_video_url(self, client: PixabayClient) -> None:
        """Test video URL selection logic."""
        videos = {
            "large": {"url": "https://example.com/large.mp4"},
            "medium": {"url": "https://example.com/medium.mp4"},
        }

        url = client._select_best_video_url(videos)
        assert url == "https://example.com/large.mp4"

    def test_select_best_video_url_fallback(self, client: PixabayClient) -> None:
        """Test video URL selection falls back to smaller sizes."""
        videos = {
            "small": {"url": "https://example.com/small.mp4"},
        }

        url = client._select_best_video_url(videos)
        assert url == "https://example.com/small.mp4"

    def test_select_best_video_url_empty(self, client: PixabayClient) -> None:
        """Test video URL selection returns None for empty dict."""
        url = client._select_best_video_url({})
        assert url is None


class TestVisualSourcingManagerWithPixabay:
    """Test VisualSourcingManager with Pixabay integration."""

    @pytest.fixture
    def mock_pixabay(self) -> AsyncMock:
        """Create a mock Pixabay client."""
        client = AsyncMock()
        client.search_videos = AsyncMock(return_value=[])
        client.search_images = AsyncMock(return_value=[])
        client.download = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def http_client(self) -> HTTPClient:
        """Create HTTP client."""
        return HTTPClient()

    @pytest.fixture
    def manager_with_all_sources(
        self,
        http_client: HTTPClient,
        mock_pixabay: AsyncMock,
    ) -> VisualSourcingManager:
        """Create a VisualSourcingManager with all sources mocked."""
        mock_pexels = AsyncMock()
        mock_pexels.search_videos = AsyncMock(return_value=[])
        mock_pexels.search_images = AsyncMock(return_value=[])
        mock_pexels.download = AsyncMock()
        mock_pexels.close = AsyncMock()

        mock_fallback = AsyncMock()
        mock_fallback.search = AsyncMock(return_value=[])
        mock_fallback.download = AsyncMock()

        mock_tavily_image = AsyncMock()
        mock_tavily_image.search = AsyncMock(return_value=[])
        mock_tavily_image.download = AsyncMock()
        mock_tavily_image.close = AsyncMock()

        mock_wan_video = AsyncMock()
        mock_wan_video.generate = AsyncMock(return_value=[])
        mock_wan_video.download = AsyncMock()
        mock_wan_video.close = AsyncMock()

        return VisualSourcingManager(
            http_client=http_client,
            config=VisualConfig(),
            pexels_client=mock_pexels,
            pixabay_client=mock_pixabay,
            tavily_image_client=mock_tavily_image,
            wan_video_source=mock_wan_video,
            fallback_generator=mock_fallback,
        )

    @pytest.mark.asyncio
    async def test_source_visuals_tries_pixabay(
        self,
        manager_with_all_sources: VisualSourcingManager,
        mock_pixabay: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test that visual sourcing tries Pixabay sources."""
        await manager_with_all_sources.source_visuals(
            keywords=["test"],
            duration_needed=10.0,
            output_dir=tmp_path,
        )

        # Should have tried Pixabay video and image sources
        mock_pixabay.search_videos.assert_called()

    @pytest.mark.asyncio
    async def test_close_closes_all_clients(
        self,
        manager_with_all_sources: VisualSourcingManager,
        mock_pixabay: AsyncMock,
    ) -> None:
        """Test that close() closes all clients including Pixabay."""
        await manager_with_all_sources.close()

        mock_pixabay.close.assert_called_once()
