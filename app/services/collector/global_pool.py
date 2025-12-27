"""Global Topic Pool for shared source collection.

This module provides Redis-based storage for topics collected from
global sources (HackerNews, Google Trends, YouTube Trending).

All channels share this pool and filter topics based on their config.
"""

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis as AsyncRedis

from app.core.logging import get_logger
from app.services.collector.base import RawTopic
from app.services.collector.sources.factory import is_global_source

logger = get_logger(__name__)


class GlobalTopicPool:
    """Redis-based pool for globally collected topics.

    Global sources (HN, Trends, YouTube) are collected once and stored here.
    Channels pull from this pool and filter based on their config.

    Keys:
        global_pool:{source_type} -> List of RawTopic JSON strings
        global_pool:{source_type}:meta -> Metadata (collected_at, count)
    """

    POOL_KEY_PREFIX = "global_pool:"
    META_KEY_SUFFIX = ":meta"
    DEFAULT_TTL_HOURS = 4  # Topics expire after 4 hours

    def __init__(self, redis: "AsyncRedis[Any]"):
        """Initialize the global pool.

        Args:
            redis: Async Redis client
        """
        self.redis = redis

    async def add_topics(
        self,
        source_type: str,
        topics: list[RawTopic],
        ttl_hours: int | None = None,
    ) -> int:
        """Add topics to the global pool.

        Replaces existing topics for the source (fresh snapshot).

        Args:
            source_type: Source type (hackernews, google_trends, etc.)
            topics: List of RawTopic to store
            ttl_hours: Cache TTL in hours (default: 4)

        Returns:
            Number of topics added
        """
        if not is_global_source(source_type):
            logger.warning(f"Attempted to add non-global source to pool: {source_type}")
            return 0

        ttl = (ttl_hours or self.DEFAULT_TTL_HOURS) * 3600
        key = f"{self.POOL_KEY_PREFIX}{source_type}"
        meta_key = f"{key}{self.META_KEY_SUFFIX}"

        # Use pipeline for atomic operation
        pipe = self.redis.pipeline()

        # Delete existing data
        pipe.delete(key)

        # Add new topics
        if topics:
            topic_jsons = [t.model_dump_json() for t in topics]
            pipe.rpush(key, *topic_jsons)
            pipe.expire(key, ttl)

        # Update metadata
        meta = {
            "collected_at": datetime.now(UTC).isoformat(),
            "count": len(topics),
            "source_type": source_type,
        }
        pipe.set(meta_key, json.dumps(meta), ex=ttl)

        await pipe.execute()

        logger.info(
            f"Added {len(topics)} topics to global pool",
            extra={"source_type": source_type, "ttl_hours": ttl_hours or self.DEFAULT_TTL_HOURS},
        )

        return len(topics)

    async def get_topics(self, source_type: str) -> list[RawTopic]:
        """Get all topics for a source from the pool.

        Args:
            source_type: Source type

        Returns:
            List of RawTopic (empty if not found or expired)
        """
        key = f"{self.POOL_KEY_PREFIX}{source_type}"
        data = await self.redis.lrange(key, 0, -1)

        if not data:
            logger.debug(f"No topics in global pool for {source_type}")
            return []

        topics = []
        for item in data:
            try:
                # Handle both bytes and str
                json_str = item.decode() if isinstance(item, bytes) else item
                topics.append(RawTopic.model_validate_json(json_str))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse topic from pool: {e}", exc_info=True)
                continue

        logger.debug(
            f"Retrieved {len(topics)} topics from global pool",
            extra={"source_type": source_type},
        )

        return topics

    async def is_fresh(self, source_type: str) -> bool:
        """Check if pool has fresh data for a source.

        Args:
            source_type: Source type

        Returns:
            True if data exists and is not expired
        """
        key = f"{self.POOL_KEY_PREFIX}{source_type}"
        return await self.redis.exists(key) > 0

    async def get_metadata(self, source_type: str) -> dict[str, Any] | None:
        """Get metadata for a source's pool data.

        Args:
            source_type: Source type

        Returns:
            Metadata dict or None if not found
        """
        key = f"{self.POOL_KEY_PREFIX}{source_type}{self.META_KEY_SUFFIX}"
        data = await self.redis.get(key)

        if not data:
            return None

        json_str = data.decode() if isinstance(data, bytes) else str(data)
        result: dict[str, Any] = json.loads(json_str)
        return result

    async def get_all_source_types(self) -> list[str]:
        """Get all source types currently in the pool.

        Returns:
            List of source type names
        """
        pattern = f"{self.POOL_KEY_PREFIX}*"
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            # Skip meta keys
            if not key_str.endswith(self.META_KEY_SUFFIX):
                source_type = key_str.replace(self.POOL_KEY_PREFIX, "")
                keys.append(source_type)
        return keys

    async def clear(self, source_type: str | None = None) -> int:
        """Clear pool data.

        Args:
            source_type: Specific source to clear, or None for all

        Returns:
            Number of keys deleted
        """
        if source_type:
            key = f"{self.POOL_KEY_PREFIX}{source_type}"
            meta_key = f"{key}{self.META_KEY_SUFFIX}"
            return await self.redis.delete(key, meta_key)

        # Clear all
        pattern = f"{self.POOL_KEY_PREFIX}*"
        keys = [key async for key in self.redis.scan_iter(match=pattern)]
        if keys:
            return await self.redis.delete(*keys)
        return 0


class ScopedSourceCache:
    """Short-term cache for scoped source collection results.

    When multiple channels request the same subreddit/gallery,
    the first request collects and caches, subsequent requests use cache.

    Keys:
        scoped_cache:{source_type}:{param_hash} -> List of RawTopic JSON
    """

    CACHE_KEY_PREFIX = "scoped_cache:"
    DEFAULT_TTL_MINUTES = 30  # Short TTL for scoped sources

    def __init__(self, redis: "AsyncRedis[Any]"):
        """Initialize the scoped cache.

        Args:
            redis: Async Redis client
        """
        self.redis = redis

    def _make_key(self, source_type: str, params: dict[str, Any]) -> str:
        """Generate cache key from source type and params.

        Args:
            source_type: Source type
            params: Collection parameters

        Returns:
            Cache key string
        """
        # Sort and format params for consistent key
        sorted_params = sorted(params.items())
        param_parts = []
        for k, v in sorted_params:
            if isinstance(v, list):
                v = ",".join(sorted(str(x) for x in v))
            param_parts.append(f"{k}={v}")
        param_str = "|".join(param_parts)

        return f"{self.CACHE_KEY_PREFIX}{source_type}:{param_str}"

    async def get(self, source_type: str, params: dict[str, Any]) -> list[RawTopic] | None:
        """Get cached topics if available.

        Args:
            source_type: Source type
            params: Collection parameters

        Returns:
            List of RawTopic if cached, None if not
        """
        key = self._make_key(source_type, params)
        data = await self.redis.get(key)

        if not data:
            return None

        json_str = data.decode() if isinstance(data, bytes) else data
        topic_jsons = json.loads(json_str)

        topics = []
        for item in topic_jsons:
            try:
                topics.append(RawTopic.model_validate_json(item))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse cached topic: {e}", exc_info=True)
                continue

        logger.debug(
            f"Cache hit for {source_type}",
            extra={"params": params, "count": len(topics)},
        )

        return topics

    async def set(
        self,
        source_type: str,
        params: dict[str, Any],
        topics: list[RawTopic],
        ttl_minutes: int | None = None,
    ) -> None:
        """Cache collected topics.

        Args:
            source_type: Source type
            params: Collection parameters
            topics: Topics to cache
            ttl_minutes: Cache TTL in minutes
        """
        key = self._make_key(source_type, params)
        ttl = (ttl_minutes or self.DEFAULT_TTL_MINUTES) * 60

        topic_jsons = [t.model_dump_json() for t in topics]
        await self.redis.setex(key, ttl, json.dumps(topic_jsons))

        logger.debug(
            f"Cached {len(topics)} topics for {source_type}",
            extra={"params": params, "ttl_minutes": ttl_minutes or self.DEFAULT_TTL_MINUTES},
        )

    async def get_or_collect(
        self,
        source_type: str,
        params: dict[str, Any],
        collector_func: Any,
        ttl_minutes: int | None = None,
    ) -> list[RawTopic]:
        """Get from cache or collect and cache.

        Args:
            source_type: Source type
            params: Collection parameters
            collector_func: Async function to collect topics
            ttl_minutes: Cache TTL

        Returns:
            List of RawTopic
        """
        # Try cache first
        cached = await self.get(source_type, params)
        if cached is not None:
            return cached

        # Collect
        topics: list[RawTopic] = await collector_func(source_type, params)

        # Cache
        await self.set(source_type, params, topics, ttl_minutes)

        return topics

    async def invalidate(self, source_type: str, params: dict[str, Any]) -> bool:
        """Invalidate cached data.

        Args:
            source_type: Source type
            params: Collection parameters

        Returns:
            True if key was deleted
        """
        key = self._make_key(source_type, params)
        return await self.redis.delete(key) > 0

    async def clear_all(self) -> int:
        """Clear all scoped cache.

        Returns:
            Number of keys deleted
        """
        pattern = f"{self.CACHE_KEY_PREFIX}*"
        keys = [key async for key in self.redis.scan_iter(match=pattern)]
        if keys:
            return await self.redis.delete(*keys)
        return 0


__all__ = [
    "is_global_source",
    "GlobalTopicPool",
    "ScopedSourceCache",
]
