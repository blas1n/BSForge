"""Unit tests for PexelsClient."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.pexels import PexelsClient, _calculate_metadata_score


@pytest.fixture
def client() -> PexelsClient:
    return PexelsClient(api_key="test-key")


class TestSelectBestVideoFile:
    """Tests for PexelsClient._select_best_video_file."""

    def test_returns_none_when_no_files(self, client: PexelsClient) -> None:
        assert client._select_best_video_file([], "portrait") is None

    def test_returns_none_when_only_sub_hd_files(self, client: PexelsClient) -> None:
        # height=854 and height=640 — both below min_height=1080
        sd_files = [
            {"width": 480, "height": 854, "quality": "sd", "link": "http://x.com/v.mp4"},
            {"width": 360, "height": 640, "quality": "sd", "link": "http://x.com/v2.mp4"},
        ]
        result = client._select_best_video_file(sd_files, "portrait", min_height=1080)
        assert result is None

    def test_returns_hd_file_when_available(self, client: PexelsClient) -> None:
        files = [
            {"width": 720, "height": 1280, "quality": "sd", "link": "http://x.com/sd.mp4"},
            {"width": 1080, "height": 1920, "quality": "hd", "link": "http://x.com/hd.mp4"},
        ]
        result = client._select_best_video_file(files, "portrait", min_height=1080)
        assert result is not None
        assert result["height"] == 1920
        assert result["link"] == "http://x.com/hd.mp4"

    def test_prefers_higher_resolution_hd(self, client: PexelsClient) -> None:
        files = [
            {"width": 1080, "height": 1920, "quality": "hd", "link": "http://x.com/fhd.mp4"},
            {"width": 720, "height": 1280, "quality": "hd", "link": "http://x.com/hd.mp4"},
        ]
        result = client._select_best_video_file(files, "portrait", min_height=1080)
        assert result is not None
        assert result["height"] == 1920

    def test_portrait_filter_excludes_landscape(self, client: PexelsClient) -> None:
        files = [
            {
                "width": 1920,
                "height": 1080,
                "quality": "hd",
                "link": "http://x.com/land.mp4",
            },  # landscape
            {
                "width": 1080,
                "height": 1920,
                "quality": "hd",
                "link": "http://x.com/port.mp4",
            },  # portrait
        ]
        result = client._select_best_video_file(files, "portrait", min_height=1080)
        assert result is not None
        assert result["width"] < result["height"]  # portrait

    def test_returns_landscape_fallback_when_no_portrait(self, client: PexelsClient) -> None:
        # All files are landscape (width > height) — portrait filter falls back to all files.
        # The landscape file has height=1080 which passes min_height.
        files = [
            {"width": 1920, "height": 1080, "quality": "hd", "link": "http://x.com/land.mp4"},
        ]
        # After portrait filter, files is empty → falls back to all files
        # The landscape file has height=1080 which passes min_height
        result = client._select_best_video_file(files, "portrait", min_height=1080)
        # Fallback to all files — landscape with height=1080 passes HD check
        assert result is not None
        assert result["width"] > result["height"]  # Verify it's actually landscape
        assert result["height"] == 1080


class TestSearchVideos:
    """Tests for PexelsClient.search_videos."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self) -> None:
        client = PexelsClient(api_key=None)
        # Ensure env var is not set
        import os

        os.environ.pop("PEXELS_API_KEY", None)
        client._api_key = None
        result = await client.search_videos("test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_video_without_hd_files(self, client: PexelsClient) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "videos": [
                {
                    "id": 123,
                    "duration": 10,
                    "url": "https://pexels.com/video/123",
                    "user": {"name": "test"},
                    "video_files": [
                        {
                            "width": 480,
                            "height": 854,
                            "quality": "sd",
                            "link": "http://x.com/sd.mp4",
                        }
                    ],
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        client._client = mock_client

        result = await client.search_videos("test", max_results=5)
        # SD-only video (height=854 < 1080) should be excluded
        assert result == []


class TestMetadataScore:
    """Tests for _calculate_metadata_score module-level function."""

    def test_empty_query_returns_zero(self) -> None:
        result = _calculate_metadata_score("", {"url": "https://example.com/photo"})
        assert result == 0.0

    def test_single_token_match_returns_one(self) -> None:
        result = _calculate_metadata_score(
            "sunset",
            {"url": "https://pexels.com/photo-sunset-beach"},
        )
        assert result == 1.0

    def test_multi_token_partial_match_returns_proportional(self) -> None:
        # "mountain sunset ocean" has 3 tokens, URL contains "sunset" and "mountain"
        result = _calculate_metadata_score(
            "mountain sunset ocean",
            {"url": "https://pexels.com/photo-mountain-sunset"},
        )
        assert result == pytest.approx(2.0 / 3.0)

    def test_no_metadata_returns_neutral(self) -> None:
        # No url, no user, no alt — should return 0.5
        result = _calculate_metadata_score("sunset", {})
        assert result == 0.5

    def test_alt_text_matching(self) -> None:
        result = _calculate_metadata_score(
            "sunset",
            {"alt": "Beautiful sunset over the ocean"},
        )
        assert result == 1.0

    def test_photographer_name_matching(self) -> None:
        result = _calculate_metadata_score(
            "john",
            {"user": {"name": "John Doe"}},
        )
        assert result == 1.0


class TestSearchImages:
    """Tests for PexelsClient.search_images."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self) -> None:
        no_key_client = PexelsClient(api_key=None)
        os.environ.pop("PEXELS_API_KEY", None)
        no_key_client._api_key = None
        result = await no_key_client.search_images("test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_search_returns_image_assets(self, client: PexelsClient) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "photos": [
                {
                    "id": 456,
                    "width": 1080,
                    "height": 1920,
                    "url": "https://pexels.com/photo/456",
                    "photographer": "Jane Doe",
                    "avg_color": "#AABBCC",
                    "src": {
                        "large2x": "https://images.pexels.com/456/large2x.jpg",
                        "large": "https://images.pexels.com/456/large.jpg",
                        "original": "https://images.pexels.com/456/original.jpg",
                    },
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        client._client = mock_client

        result = await client.search_images("nature", max_results=5)

        assert len(result) == 1
        asset = result[0]
        assert asset.type == VisualSourceType.STOCK_IMAGE
        assert asset.url == "https://images.pexels.com/456/large2x.jpg"
        assert asset.source == "pexels"
        assert asset.source_id == "456"
        assert asset.width == 1080
        assert asset.height == 1920
        assert asset.metadata["photographer"] == "Jane Doe"
        assert asset.metadata["avg_color"] == "#AABBCC"

    @pytest.mark.asyncio
    async def test_excludes_ids_in_exclude_set(self, client: PexelsClient) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "photos": [
                {
                    "id": 100,
                    "width": 1080,
                    "height": 1920,
                    "url": "https://pexels.com/photo/100",
                    "photographer": "A",
                    "src": {"large2x": "https://images.pexels.com/100.jpg"},
                },
                {
                    "id": 200,
                    "width": 1080,
                    "height": 1920,
                    "url": "https://pexels.com/photo/200",
                    "photographer": "B",
                    "src": {"large2x": "https://images.pexels.com/200.jpg"},
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        client._client = mock_client

        result = await client.search_images("nature", max_results=5, exclude_ids={"100"})

        assert len(result) == 1
        assert result[0].source_id == "200"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, client: PexelsClient) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        mock_client.is_closed = False
        client._client = mock_client

        result = await client.search_images("nature")
        assert result == []


class TestDownload:
    """Tests for PexelsClient.download."""

    @pytest.mark.asyncio
    async def test_successful_download_creates_file(
        self, client: PexelsClient, tmp_path: Path
    ) -> None:
        asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url="https://videos.pexels.com/123.mp4",
            source="pexels",
            source_id="123",
        )

        # Mock the streaming response
        mock_stream_response = AsyncMock()
        mock_stream_response.raise_for_status = MagicMock()
        mock_stream_response.aiter_bytes = MagicMock(
            return_value=AsyncIterator([b"fake video data"])
        )

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.stream = MagicMock(return_value=AsyncContextManager(mock_stream_response))
        client._client = mock_client

        result = await client.download(asset, tmp_path)

        expected_path = tmp_path / "pexels_123.mp4"
        assert result.path == expected_path
        assert expected_path.exists()
        assert expected_path.read_bytes() == b"fake video data"

    @pytest.mark.asyncio
    async def test_raises_value_error_if_no_url(self, client: PexelsClient, tmp_path: Path) -> None:
        asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url=None,
            source="pexels",
            source_id="123",
        )

        with pytest.raises(ValueError, match="Asset has no URL"):
            await client.download(asset, tmp_path)

    @pytest.mark.asyncio
    async def test_skips_download_if_file_exists(
        self, client: PexelsClient, tmp_path: Path
    ) -> None:
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://images.pexels.com/456.jpg",
            source="pexels",
            source_id="456",
        )

        # Pre-create the file
        existing_file = tmp_path / "pexels_456.jpg"
        existing_file.write_bytes(b"existing data")

        result = await client.download(asset, tmp_path)

        assert result.path == existing_file
        # File should still have original content (not re-downloaded)
        assert existing_file.read_bytes() == b"existing data"

    @pytest.mark.asyncio
    async def test_http_error_raises_runtime_error(
        self, client: PexelsClient, tmp_path: Path
    ) -> None:
        asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url="https://videos.pexels.com/fail.mp4",
            source="pexels",
            source_id="999",
        )

        mock_stream_response = AsyncMock()
        mock_stream_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.stream = MagicMock(return_value=AsyncContextManager(mock_stream_response))
        client._client = mock_client

        with pytest.raises(RuntimeError, match="Download failed"):
            await client.download(asset, tmp_path)


class TestSearch:
    """Tests for PexelsClient.search (combined search method)."""

    @pytest.mark.asyncio
    async def test_falls_back_to_images_when_not_enough_videos(self, client: PexelsClient) -> None:
        video_asset = VisualAsset(
            type=VisualSourceType.STOCK_VIDEO,
            url="https://videos.pexels.com/1.mp4",
            source="pexels",
            source_id="1",
        )
        image_asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            url="https://images.pexels.com/2.jpg",
            source="pexels",
            source_id="2",
        )

        client.search_videos = AsyncMock(return_value=[video_asset])  # type: ignore[method-assign]
        client.search_images = AsyncMock(return_value=[image_asset])  # type: ignore[method-assign]

        result = await client.search("nature", max_results=3)

        assert len(result) == 2
        assert result[0].type == VisualSourceType.STOCK_VIDEO
        assert result[1].type == VisualSourceType.STOCK_IMAGE
        # Image search should have been called with remaining count
        client.search_images.assert_called_once_with(
            query="nature",
            max_results=2,
            orientation="portrait",
        )

    @pytest.mark.asyncio
    async def test_returns_only_videos_when_enough(self, client: PexelsClient) -> None:
        videos = [
            VisualAsset(
                type=VisualSourceType.STOCK_VIDEO,
                url=f"https://videos.pexels.com/{i}.mp4",
                source="pexels",
                source_id=str(i),
            )
            for i in range(3)
        ]

        client.search_videos = AsyncMock(return_value=videos)  # type: ignore[method-assign]
        client.search_images = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await client.search("nature", max_results=3)

        assert len(result) == 3
        assert all(a.type == VisualSourceType.STOCK_VIDEO for a in result)
        # Image search should not be called since we have enough
        client.search_images.assert_not_called()


class TestClose:
    """Tests for PexelsClient.close."""

    @pytest.mark.asyncio
    async def test_closes_client_if_open(self, client: PexelsClient) -> None:
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        client._client = mock_client

        await client.close()

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_error_if_client_is_none(self) -> None:
        no_client = PexelsClient(api_key="test-key")
        no_client._client = None

        # Should not raise
        await no_client.close()


# --- Helpers for async mocking ---


class AsyncIterator:
    """Helper to create an async iterator from a list."""

    def __init__(self, items: list[bytes]) -> None:
        self._items = items
        self._index = 0

    def __aiter__(self) -> "AsyncIterator":
        return self

    async def __anext__(self) -> bytes:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class AsyncContextManager:
    """Helper to create an async context manager from a value."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        pass
