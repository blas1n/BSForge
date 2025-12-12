"""Unit tests for topic collection tasks.

Tests the Celery tasks for topic collection.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.workers.collect import (
    CollectionTaskResult,
    _get_config_class,
    _get_source_class,
)


@pytest.fixture
def channel_id() -> str:
    """Create a test channel UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def source_id() -> str:
    """Create a test source UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_sources(source_id: str) -> list[dict]:
    """Create sample source configurations."""
    return [
        {
            "type": "hackernews",
            "id": source_id,
            "config": {"limit": 10, "min_score": 50},
        },
    ]


class TestCollectionTaskResult:
    """Tests for CollectionTaskResult model."""

    def test_basic_creation(self, channel_id: str):
        """Test basic result creation."""
        result = CollectionTaskResult(
            channel_id=channel_id,
            source_results=[],
            started_at=datetime.now(UTC),
        )

        assert result.channel_id == channel_id
        assert result.total_collected == 0
        assert result.total_processed == 0
        assert result.errors == []

    def test_with_results(self, channel_id: str):
        """Test result with actual data."""
        source_results = [
            {"source_id": str(uuid.uuid4()), "collected_count": 10, "errors": []},
        ]

        result = CollectionTaskResult(
            channel_id=channel_id,
            source_results=source_results,
            total_collected=10,
            total_processed=8,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors=["One error"],
        )

        assert result.total_collected == 10
        assert result.total_processed == 8
        assert len(result.errors) == 1


class TestGetSourceClass:
    """Tests for _get_source_class()."""

    def test_hackernews_source(self):
        """Test getting HackerNews source class."""
        source_class = _get_source_class("hackernews")
        assert source_class.__name__ == "HackerNewsSource"

    def test_reddit_source(self):
        """Test getting Reddit source class."""
        source_class = _get_source_class("reddit")
        assert source_class.__name__ == "RedditSource"

    def test_rss_source(self):
        """Test getting RSS source class."""
        source_class = _get_source_class("rss")
        assert source_class.__name__ == "RSSSource"

    def test_dcinside_source(self):
        """Test getting DCInside source class."""
        source_class = _get_source_class("dcinside")
        assert source_class.__name__ == "DCInsideSource"

    def test_clien_source(self):
        """Test getting Clien source class."""
        source_class = _get_source_class("clien")
        assert source_class.__name__ == "ClienSource"

    def test_unknown_source_raises(self):
        """Test that unknown source type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _get_source_class("unknown_source")
        assert "Unknown source type" in str(exc_info.value)


class TestGetConfigClass:
    """Tests for _get_config_class()."""

    def test_hackernews_config(self):
        """Test getting HackerNews config class."""
        config_class = _get_config_class("hackernews")
        assert config_class.__name__ == "HackerNewsConfig"

    def test_reddit_config(self):
        """Test getting Reddit config class."""
        config_class = _get_config_class("reddit")
        assert config_class.__name__ == "RedditConfig"

    def test_rss_config(self):
        """Test getting RSS config class."""
        config_class = _get_config_class("rss")
        assert config_class.__name__ == "RSSConfig"

    def test_youtube_trending_config(self):
        """Test getting YouTube Trending config class."""
        config_class = _get_config_class("youtube_trending")
        assert config_class.__name__ == "YouTubeTrendingConfig"

    def test_google_trends_config(self):
        """Test getting Google Trends config class."""
        config_class = _get_config_class("google_trends")
        assert config_class.__name__ == "GoogleTrendsConfig"

    def test_dcinside_config(self):
        """Test getting DCInside config class."""
        config_class = _get_config_class("dcinside")
        assert config_class.__name__ == "DCInsideConfig"

    def test_clien_config(self):
        """Test getting Clien config class."""
        config_class = _get_config_class("clien")
        assert config_class.__name__ == "ClienConfig"

    def test_unknown_config_returns_none(self):
        """Test that unknown config type returns None."""
        config_class = _get_config_class("unknown")
        assert config_class is None


class TestCollectFromSourceAsync:
    """Tests for _collect_from_source_async()."""

    @pytest.mark.asyncio
    async def test_collect_from_source_success(self, source_id: str):
        """Test successful source collection."""
        from pydantic import HttpUrl

        from app.services.collector.base import RawTopic
        from app.workers.collect import _collect_from_source_async

        mock_topics = [
            RawTopic(
                source_id=source_id,
                source_url=HttpUrl("https://example.com/1"),
                title="Test Topic 1",
            ),
            RawTopic(
                source_id=source_id,
                source_url=HttpUrl("https://example.com/2"),
                title="Test Topic 2",
            ),
        ]

        with patch("app.workers.collect._get_source_class") as mock_source_class:
            mock_source_instance = AsyncMock()
            mock_source_instance.collect.return_value = mock_topics
            mock_source_class.return_value.return_value = mock_source_instance

            result = await _collect_from_source_async(
                source_type="hackernews",
                source_id=source_id,
                source_config={"limit": 10},
            )

            assert result.collected_count == 2
            assert result.source_name == "hackernews"
            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_collect_from_source_error(self, source_id: str):
        """Test source collection with error."""
        from app.workers.collect import _collect_from_source_async

        with patch("app.workers.collect._get_source_class") as mock_source_class:
            mock_source_class.side_effect = ValueError("Test error")

            result = await _collect_from_source_async(
                source_type="hackernews",
                source_id=source_id,
                source_config={},
            )

            assert result.collected_count == 0
            assert len(result.errors) > 0
            assert "Test error" in result.errors[0]


class TestCollectTopicsTask:
    """Tests for collect_topics Celery task."""

    def test_task_is_registered(self):
        """Test that collect_topics task is properly decorated."""
        from app.workers.collect import collect_topics

        assert hasattr(collect_topics, "name")
        assert collect_topics.name == "app.workers.collect.collect_topics"

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        from app.workers.collect import collect_topics

        assert collect_topics.max_retries == 3
        assert collect_topics.default_retry_delay == 300


class TestCollectFromSourceTask:
    """Tests for collect_from_source Celery task."""

    def test_task_is_registered(self):
        """Test that collect_from_source task is properly decorated."""
        from app.workers.collect import collect_from_source

        assert hasattr(collect_from_source, "name")
        assert collect_from_source.name == "app.workers.collect.collect_from_source"

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        from app.workers.collect import collect_from_source

        assert collect_from_source.max_retries == 3
        assert collect_from_source.default_retry_delay == 60
