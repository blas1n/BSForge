"""Unit tests for GlobalTopicPool and ScopedSourceCache.

Tests the Redis-based storage for global and scoped topic collection.
"""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import HttpUrl

from app.services.collector.base import RawTopic
from app.services.collector.global_pool import (
    GlobalTopicPool,
    ScopedSourceCache,
)
from app.services.collector.sources.factory import is_global_source


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = MagicMock()

    # Create a mock pipeline that works synchronously but with async execute
    mock_pipe = MagicMock()
    mock_pipe.delete = MagicMock(return_value=mock_pipe)
    mock_pipe.rpush = MagicMock(return_value=mock_pipe)
    mock_pipe.expire = MagicMock(return_value=mock_pipe)
    mock_pipe.set = MagicMock(return_value=mock_pipe)
    mock_pipe.execute = AsyncMock(return_value=[])

    redis.pipeline = MagicMock(return_value=mock_pipe)

    # Async methods
    redis.lrange = AsyncMock(return_value=[])
    redis.exists = AsyncMock(return_value=0)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=0)
    redis.setex = AsyncMock()
    redis.aclose = AsyncMock()

    return redis


@pytest.fixture
def sample_topics() -> list[RawTopic]:
    """Create sample RawTopic instances."""
    return [
        RawTopic(
            source_id=str(uuid.uuid4()),
            source_url=HttpUrl("https://example.com/1"),
            title="Test Topic 1",
            published_at=datetime.now(UTC),
        ),
        RawTopic(
            source_id=str(uuid.uuid4()),
            source_url=HttpUrl("https://example.com/2"),
            title="Test Topic 2",
            published_at=datetime.now(UTC),
        ),
        RawTopic(
            source_id=str(uuid.uuid4()),
            source_url=HttpUrl("https://example.com/3"),
            title="Test Topic 3",
            published_at=datetime.now(UTC),
        ),
    ]


class TestIsGlobalSource:
    """Tests for is_global_source helper from factory."""

    def test_is_global_source_true(self):
        """Test is_global_source for global sources."""
        assert is_global_source("hackernews") is True
        assert is_global_source("google_trends") is True
        assert is_global_source("youtube_trending") is True

    def test_is_global_source_false(self):
        """Test is_global_source for scoped sources."""
        assert is_global_source("reddit") is False
        assert is_global_source("dcinside") is False
        assert is_global_source("clien") is False
        assert is_global_source("ruliweb") is False
        assert is_global_source("fmkorea") is False
        assert is_global_source("rss") is False

    def test_is_global_source_unknown(self):
        """Test is_global_source for unknown source returns False."""
        assert is_global_source("unknown_source") is False


class TestGlobalTopicPoolInit:
    """Tests for GlobalTopicPool initialization."""

    def test_init(self, mock_redis):
        """Test GlobalTopicPool initialization."""
        pool = GlobalTopicPool(mock_redis)
        assert pool.redis is mock_redis

    def test_constants(self):
        """Test GlobalTopicPool class constants."""
        assert GlobalTopicPool.POOL_KEY_PREFIX == "global_pool:"
        assert GlobalTopicPool.META_KEY_SUFFIX == ":meta"
        assert GlobalTopicPool.DEFAULT_TTL_HOURS == 4


class TestGlobalTopicPoolAddTopics:
    """Tests for GlobalTopicPool.add_topics()."""

    @pytest.mark.asyncio
    async def test_add_topics_success(self, mock_redis, sample_topics):
        """Test adding topics to global pool."""
        pool = GlobalTopicPool(mock_redis)

        result = await pool.add_topics("hackernews", sample_topics)

        assert result == 3
        mock_redis.pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_topics_empty_list(self, mock_redis):
        """Test adding empty topic list."""
        pool = GlobalTopicPool(mock_redis)

        result = await pool.add_topics("hackernews", [])

        assert result == 0

    @pytest.mark.asyncio
    async def test_add_topics_non_global_source(self, mock_redis, sample_topics):
        """Test adding topics for non-global source returns 0."""
        pool = GlobalTopicPool(mock_redis)

        result = await pool.add_topics("reddit", sample_topics)

        assert result == 0
        mock_redis.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_topics_custom_ttl(self, mock_redis, sample_topics):
        """Test adding topics with custom TTL."""
        pool = GlobalTopicPool(mock_redis)

        result = await pool.add_topics("hackernews", sample_topics, ttl_hours=8)

        assert result == 3


class TestGlobalTopicPoolGetTopics:
    """Tests for GlobalTopicPool.get_topics()."""

    @pytest.mark.asyncio
    async def test_get_topics_success(self, mock_redis, sample_topics):
        """Test getting topics from pool."""
        pool = GlobalTopicPool(mock_redis)

        # Mock lrange to return serialized topics
        mock_redis.lrange.return_value = [
            topic.model_dump_json().encode() for topic in sample_topics
        ]

        result = await pool.get_topics("hackernews")

        assert len(result) == 3
        assert all(isinstance(t, RawTopic) for t in result)
        mock_redis.lrange.assert_called_once_with("global_pool:hackernews", 0, -1)

    @pytest.mark.asyncio
    async def test_get_topics_empty(self, mock_redis):
        """Test getting topics from empty pool."""
        pool = GlobalTopicPool(mock_redis)
        mock_redis.lrange.return_value = []

        result = await pool.get_topics("hackernews")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_topics_handles_invalid_json(self, mock_redis, sample_topics):
        """Test get_topics skips invalid JSON entries."""
        pool = GlobalTopicPool(mock_redis)

        mock_redis.lrange.return_value = [
            sample_topics[0].model_dump_json().encode(),
            b"invalid json",
            sample_topics[1].model_dump_json().encode(),
        ]

        result = await pool.get_topics("hackernews")

        # Should only return 2 valid topics
        assert len(result) == 2


class TestGlobalTopicPoolIsFresh:
    """Tests for GlobalTopicPool.is_fresh()."""

    @pytest.mark.asyncio
    async def test_is_fresh_true(self, mock_redis):
        """Test is_fresh returns True when data exists."""
        pool = GlobalTopicPool(mock_redis)
        mock_redis.exists.return_value = 1

        result = await pool.is_fresh("hackernews")

        assert result is True
        mock_redis.exists.assert_called_once_with("global_pool:hackernews")

    @pytest.mark.asyncio
    async def test_is_fresh_false(self, mock_redis):
        """Test is_fresh returns False when no data."""
        pool = GlobalTopicPool(mock_redis)
        mock_redis.exists.return_value = 0

        result = await pool.is_fresh("hackernews")

        assert result is False


class TestGlobalTopicPoolGetMetadata:
    """Tests for GlobalTopicPool.get_metadata()."""

    @pytest.mark.asyncio
    async def test_get_metadata_success(self, mock_redis):
        """Test getting metadata for a source."""
        pool = GlobalTopicPool(mock_redis)

        meta = {
            "collected_at": "2024-01-01T00:00:00Z",
            "count": 50,
            "source_type": "hackernews",
        }
        mock_redis.get.return_value = json.dumps(meta).encode()

        result = await pool.get_metadata("hackernews")

        assert result == meta
        mock_redis.get.assert_called_once_with("global_pool:hackernews:meta")

    @pytest.mark.asyncio
    async def test_get_metadata_not_found(self, mock_redis):
        """Test getting metadata when not found."""
        pool = GlobalTopicPool(mock_redis)
        mock_redis.get.return_value = None

        result = await pool.get_metadata("hackernews")

        assert result is None


class TestGlobalTopicPoolGetAllSourceTypes:
    """Tests for GlobalTopicPool.get_all_source_types()."""

    @pytest.mark.asyncio
    async def test_get_all_source_types(self, mock_redis):
        """Test getting all source types in pool."""
        pool = GlobalTopicPool(mock_redis)

        # Mock scan_iter to return keys
        async def mock_scan_iter(match):
            yield b"global_pool:hackernews"
            yield b"global_pool:hackernews:meta"  # Should be filtered out
            yield b"global_pool:google_trends"

        mock_redis.scan_iter = mock_scan_iter

        result = await pool.get_all_source_types()

        assert "hackernews" in result
        assert "google_trends" in result
        assert len(result) == 2  # meta key should be excluded


class TestGlobalTopicPoolClear:
    """Tests for GlobalTopicPool.clear()."""

    @pytest.mark.asyncio
    async def test_clear_specific_source(self, mock_redis):
        """Test clearing a specific source."""
        pool = GlobalTopicPool(mock_redis)
        mock_redis.delete.return_value = 2

        result = await pool.clear("hackernews")

        assert result == 2
        mock_redis.delete.assert_called_once_with(
            "global_pool:hackernews", "global_pool:hackernews:meta"
        )

    @pytest.mark.asyncio
    async def test_clear_all(self, mock_redis):
        """Test clearing all sources."""
        pool = GlobalTopicPool(mock_redis)

        async def mock_scan_iter(match):
            yield b"global_pool:hackernews"
            yield b"global_pool:google_trends"

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2

        result = await pool.clear()

        assert result == 2


class TestScopedSourceCacheInit:
    """Tests for ScopedSourceCache initialization."""

    def test_init(self, mock_redis):
        """Test ScopedSourceCache initialization."""
        cache = ScopedSourceCache(mock_redis)
        assert cache.redis is mock_redis

    def test_constants(self):
        """Test ScopedSourceCache class constants."""
        assert ScopedSourceCache.CACHE_KEY_PREFIX == "scoped_cache:"
        assert ScopedSourceCache.DEFAULT_TTL_MINUTES == 30


class TestScopedSourceCacheMakeKey:
    """Tests for ScopedSourceCache._make_key()."""

    def test_make_key_simple(self, mock_redis):
        """Test key generation with simple params."""
        cache = ScopedSourceCache(mock_redis)

        key = cache._make_key("reddit", {"subreddits": ["python"]})

        assert key.startswith("scoped_cache:reddit:")
        assert "subreddits" in key

    def test_make_key_multiple_params(self, mock_redis):
        """Test key generation with multiple params."""
        cache = ScopedSourceCache(mock_redis)

        key = cache._make_key("reddit", {"subreddits": ["python", "programming"], "limit": 25})

        assert "scoped_cache:reddit:" in key
        assert "subreddits" in key
        assert "limit" in key

    def test_make_key_consistent(self, mock_redis):
        """Test key generation is consistent regardless of param order."""
        cache = ScopedSourceCache(mock_redis)

        key1 = cache._make_key("reddit", {"a": "1", "b": "2"})
        key2 = cache._make_key("reddit", {"b": "2", "a": "1"})

        assert key1 == key2


class TestScopedSourceCacheGet:
    """Tests for ScopedSourceCache.get()."""

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, mock_redis, sample_topics):
        """Test getting cached topics."""
        cache = ScopedSourceCache(mock_redis)

        # Mock cached data
        topic_jsons = [t.model_dump_json() for t in sample_topics]
        mock_redis.get.return_value = json.dumps(topic_jsons).encode()

        result = await cache.get("reddit", {"subreddits": ["python"]})

        assert len(result) == 3
        assert all(isinstance(t, RawTopic) for t in result)

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, mock_redis):
        """Test cache miss returns None."""
        cache = ScopedSourceCache(mock_redis)
        mock_redis.get.return_value = None

        result = await cache.get("reddit", {"subreddits": ["python"]})

        assert result is None


class TestScopedSourceCacheSet:
    """Tests for ScopedSourceCache.set()."""

    @pytest.mark.asyncio
    async def test_set_topics(self, mock_redis, sample_topics):
        """Test caching topics."""
        cache = ScopedSourceCache(mock_redis)

        await cache.set("reddit", {"subreddits": ["python"]}, sample_topics)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 30 * 60  # Default 30 minutes TTL

    @pytest.mark.asyncio
    async def test_set_topics_custom_ttl(self, mock_redis, sample_topics):
        """Test caching topics with custom TTL."""
        cache = ScopedSourceCache(mock_redis)

        await cache.set("reddit", {"subreddits": ["python"]}, sample_topics, ttl_minutes=60)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 60 * 60  # 60 minutes TTL


class TestScopedSourceCacheGetOrCollect:
    """Tests for ScopedSourceCache.get_or_collect()."""

    @pytest.mark.asyncio
    async def test_get_or_collect_cache_hit(self, mock_redis, sample_topics):
        """Test get_or_collect returns cached data."""
        cache = ScopedSourceCache(mock_redis)

        # Mock cached data
        topic_jsons = [t.model_dump_json() for t in sample_topics]
        mock_redis.get.return_value = json.dumps(topic_jsons).encode()

        collector_func = AsyncMock(return_value=[])

        result = await cache.get_or_collect(
            "reddit",
            {"subreddits": ["python"]},
            collector_func,
        )

        assert len(result) == 3
        collector_func.assert_not_called()  # Collector should not be called

    @pytest.mark.asyncio
    async def test_get_or_collect_cache_miss(self, mock_redis, sample_topics):
        """Test get_or_collect calls collector on cache miss."""
        cache = ScopedSourceCache(mock_redis)
        mock_redis.get.return_value = None

        collector_func = AsyncMock(return_value=sample_topics)

        result = await cache.get_or_collect(
            "reddit",
            {"subreddits": ["python"]},
            collector_func,
        )

        assert len(result) == 3
        collector_func.assert_called_once()
        mock_redis.setex.assert_called_once()  # Should cache the results


class TestScopedSourceCacheInvalidate:
    """Tests for ScopedSourceCache.invalidate()."""

    @pytest.mark.asyncio
    async def test_invalidate_existing(self, mock_redis):
        """Test invalidating existing cache."""
        cache = ScopedSourceCache(mock_redis)
        mock_redis.delete.return_value = 1

        result = await cache.invalidate("reddit", {"subreddits": ["python"]})

        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent(self, mock_redis):
        """Test invalidating non-existent cache."""
        cache = ScopedSourceCache(mock_redis)
        mock_redis.delete.return_value = 0

        result = await cache.invalidate("reddit", {"subreddits": ["python"]})

        assert result is False


class TestScopedSourceCacheClearAll:
    """Tests for ScopedSourceCache.clear_all()."""

    @pytest.mark.asyncio
    async def test_clear_all(self, mock_redis):
        """Test clearing all cached data."""
        cache = ScopedSourceCache(mock_redis)

        async def mock_scan_iter(match):
            yield b"scoped_cache:reddit:subreddits=python"
            yield b"scoped_cache:dcinside:galleries=programming"

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2

        result = await cache.clear_all()

        assert result == 2

    @pytest.mark.asyncio
    async def test_clear_all_empty(self, mock_redis):
        """Test clearing when no cached data."""
        cache = ScopedSourceCache(mock_redis)

        async def mock_scan_iter(match):
            return
            yield  # Empty generator

        mock_redis.scan_iter = mock_scan_iter

        result = await cache.clear_all()

        assert result == 0
