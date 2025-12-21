"""Unit tests for YouTube Trending source collector.

Tests use mocked HTTP responses to avoid external API calls.
"""

import uuid
from unittest.mock import patch

import pytest

from app.config.sources import YouTubeTrendingConfig
from app.infrastructure.http_client import HTTPClient
from app.services.collector.sources.youtube_trending import YouTubeTrendingSource

from .conftest import create_mock_response


@pytest.fixture
def yt_source(source_id: uuid.UUID, mock_http_client: HTTPClient) -> YouTubeTrendingSource:
    """Create YouTube Trending source with test config including API key."""
    config = YouTubeTrendingConfig(
        regions=["KR"],
        limit=5,
        category_id=0,
        request_timeout=15.0,
        api_key="test_api_key",
    )
    return YouTubeTrendingSource(config=config, source_id=source_id, http_client=mock_http_client)


@pytest.fixture
def mock_video_response() -> dict:
    """Create a mock YouTube API response."""
    return {
        "items": [
            {
                "id": "video123",
                "snippet": {
                    "title": "Test Video Title",
                    "channelTitle": "Test Channel",
                    "channelId": "channel123",
                    "publishedAt": "2024-01-15T10:00:00Z",
                    "description": "Test video description",
                    "categoryId": "22",
                    "tags": ["tech", "programming"],
                },
                "statistics": {
                    "viewCount": "1000000",
                    "likeCount": "50000",
                    "commentCount": "5000",
                },
            },
            {
                "id": "video456",
                "snippet": {
                    "title": "Another Video",
                    "channelTitle": "Another Channel",
                    "channelId": "channel456",
                    "publishedAt": "2024-01-14T10:00:00Z",
                    "description": "Another description",
                    "categoryId": "20",
                },
                "statistics": {
                    "viewCount": "500000",
                    "likeCount": "25000",
                },
            },
        ]
    }


class TestYouTubeTrendingCollect:
    """Tests for YouTubeTrendingSource.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        yt_source: YouTubeTrendingSource,
        mock_http_client: HTTPClient,
        mock_video_response: dict,
    ):
        """Test successful collection of trending videos."""
        mock_response = create_mock_response(json_data=mock_video_response)
        mock_http_client.get.return_value = mock_response

        topics = await yt_source.collect()

        assert len(topics) == 2
        assert topics[0].title == "Test Video Title"
        assert topics[0].metrics["views"] == 1000000

    @pytest.mark.asyncio
    async def test_collect_without_api_key(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test that collection returns empty list without API key."""
        config = YouTubeTrendingConfig(regions=["KR"], limit=5)  # No api_key
        source = YouTubeTrendingSource(
            config=config, source_id=source_id, http_client=mock_http_client
        )

        # Patch get_config to not have api key
        with patch("app.services.collector.sources.youtube_trending.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            mock_config.youtube_api_key = None

            topics = await source.collect()

            assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_collect_multiple_regions(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient, mock_video_response: dict
    ):
        """Test collection from multiple regions."""
        config = YouTubeTrendingConfig(regions=["KR", "US"], limit=10, api_key="test_key")
        source = YouTubeTrendingSource(
            config=config, source_id=source_id, http_client=mock_http_client
        )

        mock_response = create_mock_response(json_data=mock_video_response)
        mock_http_client.get.return_value = mock_response

        await source.collect()

        # Should collect from both regions
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_collect_handles_api_error(
        self, yt_source: YouTubeTrendingSource, mock_http_client: HTTPClient
    ):
        """Test graceful handling of API errors."""
        mock_http_client.get.side_effect = Exception("API Error")

        topics = await yt_source.collect()

        assert len(topics) == 0  # Should return empty list on error


class TestYouTubeTrendingHealthCheck:
    """Tests for YouTubeTrendingSource.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, yt_source: YouTubeTrendingSource, mock_http_client: HTTPClient
    ):
        """Test health check returns True when API is accessible."""
        mock_response = create_mock_response(status_code=200)
        mock_http_client.get.return_value = mock_response

        result = await yt_source.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self, yt_source: YouTubeTrendingSource, mock_http_client: HTTPClient
    ):
        """Test health check returns False when API is down."""
        mock_http_client.get.side_effect = Exception("Connection failed")

        result = await yt_source.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test health check returns False without API key."""
        config = YouTubeTrendingConfig(regions=["KR"])  # No api_key
        source = YouTubeTrendingSource(
            config=config, source_id=source_id, http_client=mock_http_client
        )

        with patch("app.services.collector.sources.youtube_trending.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            mock_config.youtube_api_key = None

            result = await source.health_check()

            assert result is False


class TestYouTubeTrendingConversion:
    """Tests for video to RawTopic conversion."""

    def test_to_raw_topic_extracts_metadata(
        self, yt_source: YouTubeTrendingSource, mock_video_response: dict
    ):
        """Test that metadata is correctly extracted."""
        video = mock_video_response["items"][0]
        topic = yt_source._to_raw_topic(video, "KR")

        assert topic is not None
        assert topic.title == "Test Video Title"
        assert topic.metadata["channel_title"] == "Test Channel"
        assert topic.metadata["video_id"] == "video123"
        assert topic.metadata["category_id"] == "22"
        assert topic.metadata["region"] == "KR"

    def test_to_raw_topic_extracts_metrics(
        self, yt_source: YouTubeTrendingSource, mock_video_response: dict
    ):
        """Test metrics extraction."""
        video = mock_video_response["items"][0]
        topic = yt_source._to_raw_topic(video, "KR")

        assert topic is not None
        assert topic.metrics["views"] == 1000000
        assert topic.metrics["likes"] == 50000
        assert topic.metrics["comments"] == 5000

    def test_to_raw_topic_handles_missing_statistics(self, yt_source: YouTubeTrendingSource):
        """Test handling of video with missing statistics."""
        video = {
            "id": "minimal",
            "snippet": {
                "title": "Minimal Video",
                "channelTitle": "Channel",
                "publishedAt": "2024-01-15T10:00:00Z",
            },
        }

        topic = yt_source._to_raw_topic(video, "KR")

        assert topic is not None
        assert topic.metrics["views"] == 0
        assert topic.metrics["likes"] == 0

    def test_to_raw_topic_generates_youtube_url(
        self, yt_source: YouTubeTrendingSource, mock_video_response: dict
    ):
        """Test that YouTube watch URL is generated correctly."""
        video = mock_video_response["items"][0]
        topic = yt_source._to_raw_topic(video, "KR")

        assert topic is not None
        assert "youtube.com/watch?v=video123" in str(topic.source_url)

    def test_to_raw_topic_returns_none_for_invalid_video(self, yt_source: YouTubeTrendingSource):
        """Test that invalid videos return None."""
        # Missing id
        video_no_id = {
            "snippet": {"title": "No ID Video"},
        }
        assert yt_source._to_raw_topic(video_no_id, "KR") is None

        # Missing title
        video_no_title = {
            "id": "test123",
            "snippet": {},
        }
        assert yt_source._to_raw_topic(video_no_title, "KR") is None
