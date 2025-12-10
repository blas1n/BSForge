"""Redis client configuration and utilities.

This module provides Redis connection management and common operations.
Supports both sync and async operations.
"""

import json
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================
# Redis Clients
# ============================================

# Sync Redis client (for Celery, simple operations)
redis_client: Redis = Redis.from_url(
    str(settings.redis_url),
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_keepalive=True,
)

# Async Redis client (for FastAPI)
async_redis_client: AsyncRedis = AsyncRedis.from_url(
    str(settings.redis_url),
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_keepalive=True,
)


# ============================================
# Helper Functions
# ============================================


async def get_redis() -> AsyncRedis:
    """Get async Redis client dependency.

    Returns:
        Async Redis client

    Example:
        >>> from fastapi import Depends
        >>> async def get_cached_data(redis: AsyncRedis = Depends(get_redis)):
        ...     return await redis.get("cache_key")
    """
    return async_redis_client


def get_redis_sync() -> Redis:
    """Get sync Redis client.

    Returns:
        Sync Redis client

    Example:
        >>> redis = get_redis_sync()
        >>> redis.set("key", "value")
    """
    return redis_client


async def cache_set(key: str, value: Any, expire: int | None = None) -> bool:
    """Set value in cache with optional expiration.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized if not string)
        expire: Expiration time in seconds (optional)

    Returns:
        True if successful

    Example:
        >>> await cache_set("user:123", {"name": "John"}, expire=300)
        >>> await cache_set("counter", 42, expire=60)
    """
    try:
        # Serialize non-string values as JSON
        if not isinstance(value, str):
            value = json.dumps(value)

        result = await async_redis_client.set(key, value, ex=expire)
        logger.debug("Cache set", key=key, expire=expire)
        return bool(result)
    except Exception as e:
        logger.error("Cache set failed", key=key, error=str(e))
        return False


async def cache_get(key: str, default: Any = None) -> Any:
    """Get value from cache.

    Args:
        key: Cache key
        default: Default value if key doesn't exist

    Returns:
        Cached value (JSON deserialized if applicable) or default

    Example:
        >>> user = await cache_get("user:123")
        >>> if user:
        ...     print(user["name"])
    """
    try:
        value = await async_redis_client.get(key)
        if value is None:
            return default

        # Try to deserialize JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    except Exception as e:
        logger.error("Cache get failed", key=key, error=str(e))
        return default


async def cache_delete(key: str) -> bool:
    """Delete key from cache.

    Args:
        key: Cache key

    Returns:
        True if key was deleted

    Example:
        >>> await cache_delete("user:123")
    """
    try:
        result = await async_redis_client.delete(key)
        logger.debug("Cache delete", key=key)
        return bool(result)
    except Exception as e:
        logger.error("Cache delete failed", key=key, error=str(e))
        return False


async def cache_exists(key: str) -> bool:
    """Check if key exists in cache.

    Args:
        key: Cache key

    Returns:
        True if key exists

    Example:
        >>> if await cache_exists("user:123"):
        ...     print("User is cached")
    """
    try:
        result = await async_redis_client.exists(key)
        return bool(result)
    except Exception as e:
        logger.error("Cache exists check failed", key=key, error=str(e))
        return False


async def cache_clear_pattern(pattern: str) -> int:
    """Delete all keys matching pattern.

    Args:
        pattern: Redis key pattern (e.g., "user:*")

    Returns:
        Number of keys deleted

    Example:
        >>> deleted = await cache_clear_pattern("user:*")
        >>> print(f"Deleted {deleted} cached users")
    """
    try:
        keys = []
        async for key in async_redis_client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await async_redis_client.delete(*keys)
            logger.info("Cache pattern cleared", pattern=pattern, count=deleted)
            return deleted
        return 0
    except Exception as e:
        logger.error("Cache pattern clear failed", pattern=pattern, error=str(e))
        return 0


async def check_redis_connection() -> bool:
    """Check if Redis connection is healthy.

    Returns:
        True if connection is successful, False otherwise

    Example:
        >>> is_healthy = await check_redis_connection()
        >>> if not is_healthy:
        ...     logger.error("Redis connection failed")
    """
    try:
        await async_redis_client.ping()
        return True
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        return False


async def close_redis() -> None:
    """Close Redis connections.

    Call this when shutting down the application.

    Example:
        >>> await close_redis()
    """
    await async_redis_client.close()
    redis_client.close()
    logger.info("Redis connections closed")
