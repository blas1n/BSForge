"""Unit tests for HackerNews source collector.

Tests use mocked HTTP responses to avoid external API calls.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config.sources import HackerNewsConfig
from app.services.collector.sources.hackernews import HackerNewsSource


@pytest.fixture
def source_id() -> uuid.UUID:
    """Create a test source UUID."""
    return uuid.uuid4()


@pytest.fixture
def hn_source(source_id: uuid.UUID) -> HackerNewsSource:
    """Create HackerNews source with test config."""
    config = HackerNewsConfig(
        limit=10,
        min_score=50,
        request_timeout=15.0,
    )
    return HackerNewsSource(config=config, source_id=source_id)


@pytest.fixture
def mock_story() -> dict:
    """Create a mock HN story."""
    return {
        "id": 12345,
        "type": "story",
        "title": "Test Story Title",
        "url": "https://example.com/article",
        "score": 150,
        "by": "testuser",
        "time": 1702400000,  # Unix timestamp
        "descendants": 50,
        "text": None,
    }


@pytest.fixture
def mock_ask_hn_story() -> dict:
    """Create a mock Ask HN story (no URL)."""
    return {
        "id": 12346,
        "type": "story",
        "title": "Ask HN: What is your favorite IDE?",
        "url": None,
        "score": 200,
        "by": "asker",
        "time": 1702400000,
        "descendants": 100,
        "text": "I'm curious about what IDEs people use...",
    }


class TestHackerNewsCollect:
    """Tests for HackerNews.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_success(self, hn_source: HackerNewsSource, mock_story: dict):
        """Test successful collection of HN stories."""
        mock_top_stories = [12345, 12346, 12347]

        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock top stories response (json() and raise_for_status() are sync methods)
            top_response = AsyncMock()
            top_response.json = lambda: mock_top_stories
            top_response.raise_for_status = lambda: None

            # Mock individual story response
            story_response = AsyncMock()
            story_response.json = lambda: mock_story
            story_response.raise_for_status = lambda: None

            mock_instance.get.side_effect = [top_response] + [story_response] * 3

            topics = await hn_source.collect()

            assert len(topics) > 0
            assert topics[0].title == "Test Story Title"
            assert topics[0].metrics["score"] == 150

    @pytest.mark.asyncio
    async def test_collect_with_params_override(
        self, hn_source: HackerNewsSource, mock_story: dict
    ):
        """Test collection with parameter overrides."""
        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            top_response = AsyncMock()
            top_response.json = lambda: [12345]
            top_response.raise_for_status = lambda: None

            story_response = AsyncMock()
            story_response.json = lambda: mock_story
            story_response.raise_for_status = lambda: None

            mock_instance.get.side_effect = [top_response, story_response]

            # Override with higher min_score
            topics = await hn_source.collect(params={"limit": 5, "min_score": 100})

            assert len(topics) == 1  # Story has score 150, meets threshold

    @pytest.mark.asyncio
    async def test_collect_filters_low_score(self, hn_source: HackerNewsSource, mock_story: dict):
        """Test that low-score stories are filtered out."""
        mock_story["score"] = 10  # Below min_score of 50

        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            top_response = AsyncMock()
            top_response.json = lambda: [12345]
            top_response.raise_for_status = lambda: None

            story_response = AsyncMock()
            story_response.json = lambda: mock_story
            story_response.raise_for_status = lambda: None

            mock_instance.get.side_effect = [top_response, story_response]

            topics = await hn_source.collect()

            assert len(topics) == 0  # Filtered out due to low score

    @pytest.mark.asyncio
    async def test_collect_ask_hn_uses_hn_url(
        self, hn_source: HackerNewsSource, mock_ask_hn_story: dict
    ):
        """Test that Ask HN posts without URL use HN discussion URL."""
        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            top_response = AsyncMock()
            top_response.json = lambda: [12346]
            top_response.raise_for_status = lambda: None

            story_response = AsyncMock()
            story_response.json = lambda: mock_ask_hn_story
            story_response.raise_for_status = lambda: None

            mock_instance.get.side_effect = [top_response, story_response]

            topics = await hn_source.collect()

            assert len(topics) == 1
            assert "news.ycombinator.com" in str(topics[0].source_url)
            assert topics[0].content == "I'm curious about what IDEs people use..."


class TestHackerNewsHealthCheck:
    """Tests for HackerNews.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, hn_source: HackerNewsSource):
        """Test health check returns True when API is accessible."""
        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_instance.get.return_value = mock_response

            result = await hn_source.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, hn_source: HackerNewsSource):
        """Test health check returns False when API is down."""
        with patch("app.services.collector.sources.hackernews.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.get.side_effect = httpx.ConnectError("Connection failed")

            result = await hn_source.health_check()

            assert result is False


class TestHackerNewsConversion:
    """Tests for story to RawTopic conversion."""

    def test_to_raw_topic_extracts_metadata(self, hn_source: HackerNewsSource, mock_story: dict):
        """Test that metadata is correctly extracted."""
        topic = hn_source._to_raw_topic(mock_story)

        assert topic is not None
        assert topic.metadata["hn_id"] == 12345
        assert topic.metadata["by"] == "testuser"
        assert "news.ycombinator.com" in topic.metadata["hn_url"]

    def test_to_raw_topic_parses_timestamp(self, hn_source: HackerNewsSource, mock_story: dict):
        """Test that Unix timestamp is converted to datetime."""
        topic = hn_source._to_raw_topic(mock_story)

        assert topic is not None
        assert topic.published_at is not None
        assert isinstance(topic.published_at, datetime)
        assert topic.published_at.tzinfo == UTC

    def test_to_raw_topic_handles_missing_fields(self, hn_source: HackerNewsSource):
        """Test handling of story with missing optional fields."""
        minimal_story = {
            "id": 99999,
            "type": "story",
            "title": "Minimal Story",
        }

        topic = hn_source._to_raw_topic(minimal_story)

        assert topic is not None
        assert topic.title == "Minimal Story"
        assert topic.published_at is None
        assert topic.metrics["score"] == 0
