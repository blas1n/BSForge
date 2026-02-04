"""Unit tests for LoremFlickr/Unsplash source module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.unsplash import (
    LoremFlickrSource,
    PicsumSource,
    UnsplashSource,
)


class TestLoremFlickrSource:
    """Tests for LoremFlickrSource class."""

    @pytest.fixture
    def source(self):
        """Create LoremFlickrSource instance."""
        return LoremFlickrSource(timeout=30.0)

    @pytest.mark.asyncio
    async def test_search_portrait(self, source):
        """Test search with portrait orientation."""
        assets = await source.search("technology", max_results=3, orientation="portrait")

        assert len(assets) == 3
        for asset in assets:
            assert asset.type == VisualSourceType.STOCK_IMAGE
            assert asset.width == 1080
            assert asset.height == 1920
            assert asset.source == "loremflickr"
            assert "technology" in asset.url
            assert "1080/1920" in asset.url

    @pytest.mark.asyncio
    async def test_search_landscape(self, source):
        """Test search with landscape orientation."""
        assets = await source.search("nature", max_results=2, orientation="landscape")

        assert len(assets) == 2
        for asset in assets:
            assert asset.width == 1920
            assert asset.height == 1080
            assert "1920/1080" in asset.url

    @pytest.mark.asyncio
    async def test_search_square(self, source):
        """Test search with square orientation."""
        assets = await source.search("abstract", max_results=1, orientation="square")

        assert len(assets) == 1
        assert assets[0].width == 1080
        assert assets[0].height == 1080
        assert "1080/1080" in assets[0].url

    @pytest.mark.asyncio
    async def test_search_replaces_spaces(self, source):
        """Test that spaces are replaced with commas."""
        assets = await source.search("cat dog bird", max_results=1)

        assert len(assets) == 1
        assert "cat,dog,bird" in assets[0].url

    @pytest.mark.asyncio
    async def test_search_keywords_extracted(self, source):
        """Test that keywords are extracted from query."""
        assets = await source.search("technology computer code", max_results=1)

        assert assets[0].keywords == ["technology", "computer", "code"]

    @pytest.mark.asyncio
    async def test_search_empty_query(self, source):
        """Test search with empty query."""
        assets = await source.search("", max_results=1)

        assert len(assets) == 1
        assert assets[0].keywords == []

    @pytest.mark.asyncio
    async def test_search_lock_parameter(self, source):
        """Test that lock parameter is included for consistency."""
        assets = await source.search("test", max_results=3)

        assert "lock=0" in assets[0].url
        assert "lock=1" in assets[1].url
        assert "lock=2" in assets[2].url

    @pytest.mark.asyncio
    async def test_search_unique_source_ids(self, source):
        """Test that each asset has unique source_id."""
        assets = await source.search("test", max_results=5)

        source_ids = [a.source_id for a in assets]
        assert len(source_ids) == len(set(source_ids))  # All unique

    @pytest.mark.asyncio
    async def test_search_license_info(self, source):
        """Test that license info is set."""
        assets = await source.search("test", max_results=1)

        assert "Flickr" in assets[0].license
        assert "Creative Commons" in assets[0].license

    @pytest.mark.asyncio
    async def test_download_success(self, source, tmp_path):
        """Test successful download."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://loremflickr.com/1080/1920/test",
            width=1080,
            height=1920,
            source="loremflickr",
            source_id="flickr_test123",
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.content = b"fake image data"
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            result = await source.download(asset, tmp_path)

            assert result.path is not None
            assert result.path.suffix == ".jpg"
            assert "flickr_test123" in result.path.name

    @pytest.mark.asyncio
    async def test_download_no_url_raises(self, source, tmp_path):
        """Test download raises error when no URL."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url=None,
            width=1080,
            height=1920,
            source="loremflickr",
            source_id="test",
        )

        with pytest.raises(ValueError, match="no URL"):
            await source.download(asset, tmp_path)

    @pytest.mark.asyncio
    async def test_download_creates_output_dir(self, source, tmp_path):
        """Test that download creates output directory if needed."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://loremflickr.com/1080/1920/test",
            source="loremflickr",
            source_id="test",
        )

        output_dir = tmp_path / "nested" / "output"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.content = b"data"
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            await source.download(asset, output_dir)

            assert output_dir.exists()

    def test_get_dimensions_portrait(self, source):
        """Test portrait dimensions."""
        w, h = source._get_dimensions("portrait")
        assert w == 1080
        assert h == 1920

    def test_get_dimensions_landscape(self, source):
        """Test landscape dimensions."""
        w, h = source._get_dimensions("landscape")
        assert w == 1920
        assert h == 1080

    def test_get_dimensions_square(self, source):
        """Test square dimensions."""
        w, h = source._get_dimensions("square")
        assert w == 1080
        assert h == 1080

    def test_default_timeout(self):
        """Test default timeout value."""
        source = LoremFlickrSource()
        assert source._timeout == 30.0

    def test_custom_timeout(self):
        """Test custom timeout value."""
        source = LoremFlickrSource(timeout=60.0)
        assert source._timeout == 60.0


class TestAliases:
    """Tests for backwards compatibility aliases."""

    def test_picsum_source_alias(self):
        """Test PicsumSource is an alias."""
        assert PicsumSource is LoremFlickrSource

    def test_unsplash_source_alias(self):
        """Test UnsplashSource is an alias."""
        assert UnsplashSource is LoremFlickrSource

    def test_create_via_alias(self):
        """Test creating source via alias."""
        source = UnsplashSource(timeout=45.0)
        assert isinstance(source, LoremFlickrSource)
        assert source._timeout == 45.0
