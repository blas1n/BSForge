"""Unit tests for topic collection tasks.

Tests the Celery tasks for topic collection including:
- Global source collection
- Channel hybrid collection
- Legacy backward-compatible tasks
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import HttpUrl

from app.services.collector.base import RawTopic
from app.workers.collect import (
    ChannelCollectionResult,
    GlobalCollectionResult,
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


@pytest.fixture
def sample_topics(source_id: str) -> list[RawTopic]:
    """Create sample RawTopic instances."""
    return [
        RawTopic(
            source_id=source_id,
            source_url=HttpUrl("https://example.com/1"),
            title="Test Topic 1",
            published_at=datetime.now(UTC),
        ),
        RawTopic(
            source_id=source_id,
            source_url=HttpUrl("https://example.com/2"),
            title="Test Topic 2",
            published_at=datetime.now(UTC),
        ),
    ]


class TestGlobalCollectionResult:
    """Tests for GlobalCollectionResult model."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = GlobalCollectionResult(
            source_results={},
            started_at=datetime.now(UTC),
        )

        assert result.source_results == {}
        assert result.total_collected == 0
        assert result.errors == []
        assert result.completed_at is None

    def test_with_results(self):
        """Test result with actual data."""
        result = GlobalCollectionResult(
            source_results={
                "hackernews": 30,
                "google_trends": 20,
                "youtube_trending": 50,
            },
            total_collected=100,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors=["One minor error"],
        )

        assert result.total_collected == 100
        assert len(result.source_results) == 3
        assert result.source_results["hackernews"] == 30
        assert len(result.errors) == 1


class TestChannelCollectionResult:
    """Tests for ChannelCollectionResult model."""

    def test_basic_creation(self, channel_id: str):
        """Test basic result creation."""
        result = ChannelCollectionResult(
            channel_id=channel_id,
            started_at=datetime.now(UTC),
        )

        assert result.channel_id == channel_id
        assert result.global_topics == 0
        assert result.scoped_topics == 0
        assert result.total_collected == 0
        assert result.total_processed == 0
        assert result.errors == []

    def test_with_results(self, channel_id: str):
        """Test result with actual data."""
        result = ChannelCollectionResult(
            channel_id=channel_id,
            global_topics=50,
            scoped_topics=30,
            total_collected=80,
            total_processed=75,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors=["One error"],
        )

        assert result.global_topics == 50
        assert result.scoped_topics == 30
        assert result.total_collected == 80
        assert result.total_processed == 75
        assert len(result.errors) == 1


class TestCollectGlobalSourcesTask:
    """Tests for collect_global_sources Celery task."""

    def test_task_is_registered(self):
        """Test that collect_global_sources task is properly decorated."""
        from app.workers.collect import collect_global_sources

        assert hasattr(collect_global_sources, "name")
        assert collect_global_sources.name == "app.workers.collect.collect_global_sources"

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        from app.workers.collect import collect_global_sources

        assert collect_global_sources.max_retries == 3
        assert collect_global_sources.default_retry_delay == 300


class TestCollectChannelTopicsTask:
    """Tests for collect_channel_topics Celery task."""

    def test_task_is_registered(self):
        """Test that collect_channel_topics task is properly decorated."""
        from app.workers.collect import collect_channel_topics

        assert hasattr(collect_channel_topics, "name")
        assert collect_channel_topics.name == "app.workers.collect.collect_channel_topics"

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        from app.workers.collect import collect_channel_topics

        assert collect_channel_topics.max_retries == 3
        assert collect_channel_topics.default_retry_delay == 300


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


class TestCollectGlobalSourcesAsync:
    """Tests for _collect_global_sources_async()."""

    @pytest.mark.asyncio
    async def test_collect_global_sources_async(self, sample_topics):
        """Test collecting from all global sources."""
        from app.workers.collect import _collect_global_sources_async

        # Mock container and its dependencies
        mock_http_client = MagicMock()
        mock_pool = AsyncMock()
        mock_pool.add_topics = AsyncMock()

        mock_container = MagicMock()
        mock_container.infrastructure.http_client.return_value = mock_http_client
        mock_container.services.global_topic_pool.return_value = mock_pool

        mock_source = AsyncMock()
        mock_source.collect.return_value = sample_topics

        with (
            patch("app.workers.collect.get_container", return_value=mock_container),
            patch("app.workers.collect.create_source", return_value=mock_source),
            patch(
                "app.workers.collect.get_global_source_names",
                return_value=["hackernews", "google_trends", "youtube_trending"],
            ),
        ):
            result = await _collect_global_sources_async()

            assert isinstance(result, GlobalCollectionResult)
            assert result.completed_at is not None
            # 3 global sources: hackernews, google_trends, youtube_trending
            assert len(result.source_results) == 3

    @pytest.mark.asyncio
    async def test_collect_global_sources_handles_errors(self):
        """Test that errors are captured, not raised."""
        from app.workers.collect import _collect_global_sources_async

        mock_http_client = MagicMock()
        mock_pool = AsyncMock()

        mock_container = MagicMock()
        mock_container.infrastructure.http_client.return_value = mock_http_client
        mock_container.services.global_topic_pool.return_value = mock_pool

        with (
            patch("app.workers.collect.get_container", return_value=mock_container),
            patch(
                "app.workers.collect.create_source",
                side_effect=Exception("Test error"),
            ),
            patch(
                "app.workers.collect.get_global_source_names",
                return_value=["hackernews"],
            ),
        ):
            result = await _collect_global_sources_async()

            assert isinstance(result, GlobalCollectionResult)
            assert len(result.errors) > 0
            assert result.total_collected == 0


class TestCollectChannelTopicsAsync:
    """Tests for _collect_channel_topics_async()."""

    @pytest.mark.asyncio
    async def test_collect_channel_topics_async(self, channel_id, sample_topics):
        """Test hybrid collection for a channel."""
        from app.workers.collect import _collect_channel_topics_async

        mock_http_client = MagicMock()
        mock_pool = AsyncMock()
        mock_pool.get_topics.return_value = sample_topics

        mock_scoped_cache = AsyncMock()
        mock_scoped_cache.get_or_collect.return_value = sample_topics

        mock_normalizer = AsyncMock()
        mock_normalizer.normalize.return_value = MagicMock()

        mock_deduplicator = AsyncMock()
        mock_deduplicator.is_duplicate.return_value = MagicMock(is_duplicate=False)

        mock_scorer = MagicMock()
        mock_scorer.score.return_value = MagicMock()

        mock_container = MagicMock()
        mock_container.infrastructure.http_client.return_value = mock_http_client
        mock_container.services.global_topic_pool.return_value = mock_pool
        mock_container.services.scoped_source_cache.return_value = mock_scoped_cache
        mock_container.services.topic_normalizer.return_value = mock_normalizer
        mock_container.services.topic_deduplicator.return_value = mock_deduplicator
        mock_container.services.topic_scorer.return_value = mock_scorer

        with (
            patch("app.workers.collect.get_container", return_value=mock_container),
            patch("app.workers.collect.is_global_source", return_value=True),
        ):
            result = await _collect_channel_topics_async(
                channel_id=channel_id,
                global_sources=["hackernews"],
                scoped_sources=[],
            )

            assert isinstance(result, ChannelCollectionResult)
            assert result.channel_id == channel_id
            assert result.completed_at is not None
