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

    def test_youtube_trending_source(self):
        """Test getting YouTube Trending source class."""
        source_class = _get_source_class("youtube_trending")
        assert source_class.__name__ == "YouTubeTrendingSource"

    def test_google_trends_source(self):
        """Test getting Google Trends source class."""
        source_class = _get_source_class("google_trends")
        assert source_class.__name__ == "GoogleTrendsSource"

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


class TestCollectSourceTopicsAsync:
    """Tests for _collect_source_topics()."""

    @pytest.mark.asyncio
    async def test_collect_source_topics_success(self, sample_topics):
        """Test successful source collection."""
        from app.workers.collect import _collect_source_topics

        with patch("app.workers.collect._get_source_class") as mock_source_class:
            mock_source_instance = AsyncMock()
            mock_source_instance.collect.return_value = sample_topics
            mock_source_class.return_value.return_value = mock_source_instance

            result = await _collect_source_topics(
                source_type="hackernews",
                source_config={"limit": 10},
            )

            assert len(result) == 2
            assert all(isinstance(t, RawTopic) for t in result)

    @pytest.mark.asyncio
    async def test_collect_source_topics_error(self):
        """Test source collection with error returns empty list."""
        from app.workers.collect import _collect_source_topics

        with patch("app.workers.collect._get_source_class") as mock_source_class:
            mock_source_class.side_effect = ValueError("Test error")

            result = await _collect_source_topics(
                source_type="hackernews",
                source_config={},
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_collect_source_topics_no_config_class(self):
        """Test collection with unknown source type."""
        from app.workers.collect import _collect_source_topics

        with patch("app.workers.collect._get_config_class", return_value=None):
            result = await _collect_source_topics(
                source_type="unknown",
                source_config={},
            )

            assert result == []


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

        mock_redis = AsyncMock()
        mock_redis.pipeline.return_value = AsyncMock()
        mock_redis.pipeline.return_value.execute = AsyncMock()
        # Support async context manager
        mock_redis.__aenter__.return_value = mock_redis
        mock_redis.__aexit__.return_value = None

        with (
            patch("app.workers.collect._collect_source_topics", return_value=sample_topics),
            patch("app.workers.collect.AsyncRedis.from_url", return_value=mock_redis),
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

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        # Support async context manager
        mock_redis.__aenter__.return_value = mock_redis
        mock_redis.__aexit__.return_value = None

        with (
            patch(
                "app.workers.collect._collect_source_topics",
                side_effect=Exception("Test error"),
            ),
            patch("app.workers.collect.AsyncRedis.from_url", return_value=mock_redis),
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

        mock_redis = AsyncMock()
        mock_redis.lrange.return_value = [t.model_dump_json().encode() for t in sample_topics]
        mock_redis.get.return_value = None
        # Support async context manager
        mock_redis.__aenter__.return_value = mock_redis
        mock_redis.__aexit__.return_value = None

        with (
            patch("app.workers.collect.AsyncRedis.from_url", return_value=mock_redis),
            patch("app.workers.collect._collect_source_topics", return_value=sample_topics),
            patch("app.config.DedupConfig"),
            patch("app.config.ScoringConfig"),
            patch("app.services.collector.deduplicator.TopicDeduplicator") as mock_dedup,
            patch("app.services.collector.normalizer.TopicNormalizer") as mock_norm,
            patch("app.services.collector.scorer.TopicScorer") as mock_scorer,
        ):
            # Setup mocks
            mock_dedup_instance = AsyncMock()
            mock_dedup_instance.is_duplicate.return_value = MagicMock(is_duplicate=False)
            mock_dedup.return_value = mock_dedup_instance

            mock_norm_instance = AsyncMock()
            mock_norm_instance.normalize.return_value = MagicMock()
            mock_norm.return_value = mock_norm_instance

            mock_scorer_instance = MagicMock()
            mock_scorer_instance.score.return_value = MagicMock()
            mock_scorer.return_value = mock_scorer_instance

            result = await _collect_channel_topics_async(
                channel_id=channel_id,
                global_sources=["hackernews"],
                scoped_sources=[{"type": "reddit", "params": {"subreddits": ["python"]}}],
            )

            assert isinstance(result, ChannelCollectionResult)
            assert result.channel_id == channel_id
            assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_collect_channel_topics_with_filters(self, channel_id, sample_topics):
        """Test hybrid collection with filters applied."""
        from app.workers.collect import _collect_channel_topics_async

        # Create topics with specific titles for filtering
        topics_with_titles = [
            RawTopic(
                source_id=str(uuid.uuid4()),
                source_url=HttpUrl("https://example.com/1"),
                title="AI and Machine Learning",
            ),
            RawTopic(
                source_id=str(uuid.uuid4()),
                source_url=HttpUrl("https://example.com/2"),
                title="Just a random topic",
            ),
        ]

        mock_redis = AsyncMock()
        mock_redis.lrange.return_value = [t.model_dump_json().encode() for t in topics_with_titles]
        mock_redis.get.return_value = None
        mock_redis.aclose = AsyncMock()
        # Support async context manager
        mock_redis.__aenter__.return_value = mock_redis
        mock_redis.__aexit__.return_value = None

        with (patch("app.workers.collect.AsyncRedis.from_url", return_value=mock_redis),):
            result = await _collect_channel_topics_async(
                channel_id=channel_id,
                global_sources=["hackernews"],
                scoped_sources=[],
                filters={"include": ["AI"]},
            )

            assert isinstance(result, ChannelCollectionResult)
            # Only "AI and Machine Learning" should pass the filter
            assert result.global_topics == 1
