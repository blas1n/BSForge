"""Redis client configuration and utilities.

This module provides Redis connection management and common operations.
Supports both sync and async operations with lazy initialization.

NOTE: For dependency injection, prefer using the container:
    from app.core.container import container, get_redis

    # In FastAPI endpoints
    async def endpoint(redis: AsyncRedis = Depends(get_redis)):
        ...

    # In services (DI via constructor)
    class MyService:
        def __init__(self, redis: AsyncRedis):
            self.redis = redis

    # Instantiate via container
    service = container.my_service()

The RedisManager and utilities in this module (cache_set, cache_get, etc.)
remain available for standalone scripts or when direct Redis access is needed.
"""

import json
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisManager:
    """Manages Redis client connections with lazy initialization.

    Provides singleton access to both sync and async Redis clients.
    Connections are created on first access, not at module load time.

    Example:
        >>> redis_manager = RedisManager()
        >>> async_client = redis_manager.async_client
        >>> sync_client = redis_manager.sync_client
    """

    _instance: "RedisManager | None" = None
    _async_client: AsyncRedis | None = None
    _sync_client: Redis | None = None

    def __new__(cls) -> "RedisManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def async_client(self) -> AsyncRedis:
        """Get async Redis client (lazy initialization).

        Returns:
            Async Redis client instance
        """
        if self._async_client is None:
            self._async_client = AsyncRedis.from_url(
                str(settings.redis_url),
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            logger.debug("Async Redis client initialized")
        return self._async_client

    @property
    def sync_client(self) -> Redis:
        """Get sync Redis client (lazy initialization).

        Returns:
            Sync Redis client instance
        """
        if self._sync_client is None:
            self._sync_client = Redis.from_url(
                str(settings.redis_url),
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            logger.debug("Sync Redis client initialized")
        return self._sync_client

    async def close(self) -> None:
        """Close all Redis connections."""
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None
        logger.info("Redis connections closed")

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing).

        This closes existing connections and clears the singleton.
        """
        if cls._instance is not None:
            if cls._async_client is not None:
                # Note: Can't await here, caller should close async client first
                cls._async_client = None
            if cls._sync_client is not None:
                cls._sync_client.close()
                cls._sync_client = None
            cls._instance = None


# Global manager instance
redis_manager = RedisManager()


# ============================================
# FastAPI Dependency Functions
# ============================================


async def get_redis() -> AsyncRedis:
    """Get async Redis client as FastAPI dependency.

    Returns:
        Async Redis client

    Example:
        >>> from fastapi import Depends
        >>> async def get_cached_data(redis: AsyncRedis = Depends(get_redis)):
        ...     return await redis.get("cache_key")
    """
    return redis_manager.async_client


def get_redis_sync() -> Redis:
    """Get sync Redis client.

    Returns:
        Sync Redis client

    Example:
        >>> redis = get_redis_sync()
        >>> redis.set("key", "value")
    """
    return redis_manager.sync_client


# ============================================
# Cache Helper Functions
# ============================================


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
        client = redis_manager.async_client
        # Serialize non-string values as JSON
        if not isinstance(value, str):
            value = json.dumps(value)

        result = await client.set(key, value, ex=expire)
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
        client = redis_manager.async_client
        value = await client.get(key)
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
        client = redis_manager.async_client
        result = await client.delete(key)
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
        client = redis_manager.async_client
        result = await client.exists(key)
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
        client = redis_manager.async_client
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await client.delete(*keys)
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
        client = redis_manager.async_client
        await client.ping()
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
    await redis_manager.close()
