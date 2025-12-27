"""Redis client utilities.

This module provides Redis cache helper functions for use with DI-injected clients.
All Redis client lifecycle management is handled by the DI container.

For Redis clients, use dependency injection:
    - FastAPI: Use Depends(get_redis) from app.core.container
    - Services: Accept Redis[Any] in constructor

The cache helper functions in this module are designed to work with
DI-injected clients for standalone scripts or utility operations.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


async def cache_set(client: Redis[Any], key: str, value: Any, expire: int | None = None) -> bool:
    """Set value in cache with optional expiration.

    Args:
        client: Async Redis client (from DI)
        key: Cache key
        value: Value to cache (will be JSON serialized if not string)
        expire: Expiration time in seconds (optional)

    Returns:
        True if successful

    Example:
        >>> redis = container.redis()
        >>> await cache_set(redis, "user:123", {"name": "John"}, expire=300)
    """
    try:
        # Serialize non-string values as JSON
        if not isinstance(value, str):
            value = json.dumps(value)

        result = await client.set(key, value, ex=expire)
        logger.debug("Cache set", key=key, expire=expire)
        return bool(result)
    except Exception as e:
        logger.error("Cache set failed", key=key, error=str(e), exc_info=True)
        return False


async def cache_get(client: Redis[Any], key: str, default: Any = None) -> Any:
    """Get value from cache.

    Args:
        client: Async Redis client (from DI)
        key: Cache key
        default: Default value if key doesn't exist

    Returns:
        Cached value (JSON deserialized if applicable) or default

    Example:
        >>> redis = container.redis()
        >>> user = await cache_get(redis, "user:123")
    """
    try:
        value = await client.get(key)
        if value is None:
            return default

        # Try to deserialize JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    except Exception as e:
        logger.error("Cache get failed", key=key, error=str(e), exc_info=True)
        return default


async def cache_delete(client: Redis[Any], key: str) -> bool:
    """Delete key from cache.

    Args:
        client: Async Redis client (from DI)
        key: Cache key

    Returns:
        True if key was deleted

    Example:
        >>> redis = container.redis()
        >>> await cache_delete(redis, "user:123")
    """
    try:
        result = await client.delete(key)
        logger.debug("Cache delete", key=key)
        return bool(result)
    except Exception as e:
        logger.error("Cache delete failed", key=key, error=str(e), exc_info=True)
        return False


async def cache_exists(client: Redis[Any], key: str) -> bool:
    """Check if key exists in cache.

    Args:
        client: Async Redis client (from DI)
        key: Cache key

    Returns:
        True if key exists

    Example:
        >>> redis = container.redis()
        >>> if await cache_exists(redis, "user:123"):
        ...     print("User is cached")
    """
    try:
        result = await client.exists(key)
        return bool(result)
    except Exception as e:
        logger.error("Cache exists check failed", key=key, error=str(e), exc_info=True)
        return False


async def cache_clear_pattern(client: Redis[Any], pattern: str) -> int:
    """Delete all keys matching pattern.

    Args:
        client: Async Redis client (from DI)
        pattern: Redis key pattern (e.g., "user:*")

    Returns:
        Number of keys deleted

    Example:
        >>> redis = container.redis()
        >>> deleted = await cache_clear_pattern(redis, "user:*")
    """
    try:
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await client.delete(*keys)
            logger.info("Cache pattern cleared", pattern=pattern, count=deleted)
            return deleted
        return 0
    except Exception as e:
        logger.error("Cache pattern clear failed", pattern=pattern, error=str(e), exc_info=True)
        return 0


async def check_redis_connection(client: Redis[Any]) -> bool:
    """Check if Redis connection is healthy.

    Args:
        client: Async Redis client (from DI)

    Returns:
        True if connection is successful, False otherwise

    Example:
        >>> redis = container.redis()
        >>> is_healthy = await check_redis_connection(redis)
    """
    try:
        await client.ping()
        return True
    except Exception as e:
        logger.error("Redis health check failed", error=str(e), exc_info=True)
        return False
