"""Unit tests for Redis cache helper functions."""

import json
from unittest.mock import AsyncMock

import pytest

from app.core.redis import (
    cache_clear_pattern,
    cache_delete,
    cache_exists,
    cache_get,
    cache_set,
    check_redis_connection,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    client = AsyncMock()
    return client


class TestCacheSet:
    """Tests for cache_set function."""

    @pytest.mark.asyncio
    async def test_set_string_value(self, mock_redis):
        """Test setting a string value."""
        mock_redis.set.return_value = True

        result = await cache_set(mock_redis, "key1", "value1")

        assert result is True
        mock_redis.set.assert_called_once_with("key1", "value1", ex=None)

    @pytest.mark.asyncio
    async def test_set_dict_value_serializes_to_json(self, mock_redis):
        """Test that dict values are JSON serialized."""
        mock_redis.set.return_value = True
        data = {"name": "John", "age": 30}

        result = await cache_set(mock_redis, "user:123", data)

        assert result is True
        mock_redis.set.assert_called_once_with("user:123", json.dumps(data), ex=None)

    @pytest.mark.asyncio
    async def test_set_list_value_serializes_to_json(self, mock_redis):
        """Test that list values are JSON serialized."""
        mock_redis.set.return_value = True
        data = [1, 2, 3, "four"]

        result = await cache_set(mock_redis, "items", data)

        assert result is True
        mock_redis.set.assert_called_once_with("items", json.dumps(data), ex=None)

    @pytest.mark.asyncio
    async def test_set_with_expiration(self, mock_redis):
        """Test setting value with expiration time."""
        mock_redis.set.return_value = True

        result = await cache_set(mock_redis, "key", "value", expire=300)

        assert result is True
        mock_redis.set.assert_called_once_with("key", "value", ex=300)

    @pytest.mark.asyncio
    async def test_set_returns_false_on_exception(self, mock_redis):
        """Test that exception returns False."""
        mock_redis.set.side_effect = Exception("Connection error")

        result = await cache_set(mock_redis, "key", "value")

        assert result is False

    @pytest.mark.asyncio
    async def test_set_integer_value(self, mock_redis):
        """Test setting an integer value (serialized as JSON)."""
        mock_redis.set.return_value = True

        result = await cache_set(mock_redis, "count", 42)

        assert result is True
        mock_redis.set.assert_called_once_with("count", "42", ex=None)


class TestCacheGet:
    """Tests for cache_get function."""

    @pytest.mark.asyncio
    async def test_get_string_value(self, mock_redis):
        """Test getting a string value that's not JSON."""
        mock_redis.get.return_value = "simple string"

        result = await cache_get(mock_redis, "key")

        assert result == "simple string"

    @pytest.mark.asyncio
    async def test_get_json_value_deserializes(self, mock_redis):
        """Test that JSON values are deserialized."""
        mock_redis.get.return_value = '{"name": "John", "age": 30}'

        result = await cache_get(mock_redis, "user:123")

        assert result == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_get_list_value_deserializes(self, mock_redis):
        """Test that JSON arrays are deserialized."""
        mock_redis.get.return_value = "[1, 2, 3]"

        result = await cache_get(mock_redis, "items")

        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_get_returns_default_when_key_not_found(self, mock_redis):
        """Test returning default value when key doesn't exist."""
        mock_redis.get.return_value = None

        result = await cache_get(mock_redis, "nonexistent", default="fallback")

        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_get_returns_none_default(self, mock_redis):
        """Test default value is None when not specified."""
        mock_redis.get.return_value = None

        result = await cache_get(mock_redis, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_default_on_exception(self, mock_redis):
        """Test that exception returns default value."""
        mock_redis.get.side_effect = Exception("Connection error")

        result = await cache_get(mock_redis, "key", default="error_fallback")

        assert result == "error_fallback"


class TestCacheDelete:
    """Tests for cache_delete function."""

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, mock_redis):
        """Test deleting an existing key."""
        mock_redis.delete.return_value = 1

        result = await cache_delete(mock_redis, "key")

        assert result is True
        mock_redis.delete.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, mock_redis):
        """Test deleting a non-existent key."""
        mock_redis.delete.return_value = 0

        result = await cache_delete(mock_redis, "nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_false_on_exception(self, mock_redis):
        """Test that exception returns False."""
        mock_redis.delete.side_effect = Exception("Connection error")

        result = await cache_delete(mock_redis, "key")

        assert result is False


class TestCacheExists:
    """Tests for cache_exists function."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing_key(self, mock_redis):
        """Test that existing key returns True."""
        mock_redis.exists.return_value = 1

        result = await cache_exists(mock_redis, "key")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_nonexistent_key(self, mock_redis):
        """Test that non-existent key returns False."""
        mock_redis.exists.return_value = 0

        result = await cache_exists(mock_redis, "nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_exception(self, mock_redis):
        """Test that exception returns False."""
        mock_redis.exists.side_effect = Exception("Connection error")

        result = await cache_exists(mock_redis, "key")

        assert result is False


class TestCacheClearPattern:
    """Tests for cache_clear_pattern function."""

    @pytest.mark.asyncio
    async def test_clear_pattern_deletes_matching_keys(self, mock_redis):
        """Test clearing keys matching a pattern."""

        # Mock scan_iter to return async iterator
        async def mock_scan_iter(match):
            for key in ["user:1", "user:2", "user:3"]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 3

        result = await cache_clear_pattern(mock_redis, "user:*")

        assert result == 3
        mock_redis.delete.assert_called_once_with("user:1", "user:2", "user:3")

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_when_no_matches(self, mock_redis):
        """Test that no matches returns zero."""

        async def mock_scan_iter(match):
            return
            yield  # noqa: B901

        mock_redis.scan_iter = mock_scan_iter

        result = await cache_clear_pattern(mock_redis, "nonexistent:*")

        assert result == 0
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_on_exception(self, mock_redis):
        """Test that exception returns zero."""

        async def mock_scan_iter(match):
            raise Exception("Connection error")
            yield  # noqa: B901

        mock_redis.scan_iter = mock_scan_iter

        result = await cache_clear_pattern(mock_redis, "user:*")

        assert result == 0


class TestCheckRedisConnection:
    """Tests for check_redis_connection function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_ping_succeeds(self, mock_redis):
        """Test that successful ping returns True."""
        mock_redis.ping.return_value = True

        result = await check_redis_connection(mock_redis)

        assert result is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_ping_fails(self, mock_redis):
        """Test that failed ping returns False."""
        mock_redis.ping.side_effect = Exception("Connection refused")

        result = await check_redis_connection(mock_redis)

        assert result is False
