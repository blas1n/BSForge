"""Unit tests for PexelsClient."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generator.visual.pexels import PexelsClient


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
        assert (
            result is not None
        )  # fallback to all files, landscape with height=1080 passes HD check


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
                            "width": 720,
                            "height": 1280,
                            "quality": "sd",
                            "link": "http://x.com/sd.mp4",
                        }
                    ],
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_client

        result = await client.search_videos("test", max_results=5)
        # SD-only video should be excluded
        assert result == []
