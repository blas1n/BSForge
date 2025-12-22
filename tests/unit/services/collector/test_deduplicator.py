"""Unit tests for TopicDeduplicator.

Tests cover:
- Hash exact match detection
- Topic marking
- Configuration options
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl
from redis.asyncio import Redis as AsyncRedis

from app.config import DedupConfig
from app.services.collector.base import NormalizedTopic
from app.services.collector.deduplicator import (
    DedupReason,
    DedupResult,
    TopicDeduplicator,
)


def create_normalized_topic(
    title: str = "Test Topic",
    content_hash: str | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic."""
    return NormalizedTopic(
        source_id=uuid.uuid4(),
        source_url=HttpUrl("https://example.com/topic"),
        title_original=title,
        title_normalized=title.lower(),
        summary=f"Summary of {title}",
        terms=["tech", "test", "topic"],
        entities={},
        language="en",
        published_at=datetime.now(UTC),
        content_hash=content_hash or f"hash_{uuid.uuid4().hex[:8]}",
        metrics={"normalized_score": 0.5},
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client."""
    redis = AsyncMock(spec=AsyncRedis)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def deduplicator(mock_redis: AsyncMock) -> TopicDeduplicator:
    """Create a TopicDeduplicator with mock Redis."""
    return TopicDeduplicator(redis=mock_redis)


@pytest.fixture
def deduplicator_with_config(mock_redis: AsyncMock) -> TopicDeduplicator:
    """Create a TopicDeduplicator with custom config."""
    config = DedupConfig(hash_ttl_days=14)
    return TopicDeduplicator(redis=mock_redis, config=config)


class TestHashMatch:
    """Tests for hash exact match detection."""

    @pytest.mark.asyncio
    async def test_no_duplicate_when_hash_not_found(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that topic is not duplicate when hash is not in Redis."""
        topic = create_normalized_topic()
        mock_redis.get.return_value = None

        result = await deduplicator.is_duplicate(topic, "channel-1")

        assert result.is_duplicate is False
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_duplicate_when_hash_found(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that topic is duplicate when hash exists in Redis."""
        topic = create_normalized_topic(content_hash="existing_hash")
        mock_redis.get.return_value = "Existing Topic Title"

        result = await deduplicator.is_duplicate(topic, "channel-1")

        assert result.is_duplicate is True
        assert result.duplicate_of == "existing_hash"
        assert result.reason == DedupReason.EXACT_HASH

    @pytest.mark.asyncio
    async def test_hash_key_includes_channel_id(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that hash key is scoped by channel ID."""
        topic = create_normalized_topic(content_hash="test_hash")

        await deduplicator.is_duplicate(topic, "channel-123")

        expected_key = "dedup:hash:channel-123:test_hash"
        mock_redis.get.assert_called_with(expected_key)

    @pytest.mark.asyncio
    async def test_different_channels_have_separate_hashes(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that same topic in different channels is not a duplicate."""
        topic = create_normalized_topic(content_hash="shared_hash")

        # First channel: hash exists
        mock_redis.get.return_value = "Title"
        result1 = await deduplicator.is_duplicate(topic, "channel-1")
        assert result1.is_duplicate is True

        # Second channel: hash doesn't exist
        mock_redis.get.return_value = None
        result2 = await deduplicator.is_duplicate(topic, "channel-2")
        assert result2.is_duplicate is False


class TestMarkAsSeen:
    """Tests for marking topics as seen."""

    @pytest.mark.asyncio
    async def test_mark_stores_hash_in_redis(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that mark_as_seen stores hash in Redis."""
        topic = create_normalized_topic(title="Test Topic", content_hash="mark_test_hash")

        await deduplicator.mark_as_seen(topic, "channel-1")

        # Check setex was called for hash
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "dedup:hash:channel-1:mark_test_hash"
        assert call_args[0][2] == "test topic"  # title_normalized

    @pytest.mark.asyncio
    async def test_mark_uses_default_ttl(
        self, deduplicator: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that default TTL (7 days) is used."""
        topic = create_normalized_topic()

        await deduplicator.mark_as_seen(topic, "channel-1")

        # 7 days in seconds
        expected_ttl = 7 * 24 * 60 * 60
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == expected_ttl

    @pytest.mark.asyncio
    async def test_mark_uses_config_ttl(
        self, deduplicator_with_config: TopicDeduplicator, mock_redis: AsyncMock
    ):
        """Test that TTL is taken from config."""
        topic = create_normalized_topic()

        await deduplicator_with_config.mark_as_seen(topic, "channel-1")

        # 14 days in seconds
        expected_ttl = 14 * 24 * 60 * 60
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == expected_ttl


class TestDedupConfig:
    """Tests for DedupConfig configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DedupConfig()

        assert config.hash_ttl_days == 7

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DedupConfig(hash_ttl_days=14)

        assert config.hash_ttl_days == 14

    def test_config_validation_min(self):
        """Test minimum hash_ttl_days validation."""
        with pytest.raises(ValueError):
            DedupConfig(hash_ttl_days=0)

    def test_config_validation_max(self):
        """Test maximum hash_ttl_days validation."""
        with pytest.raises(ValueError):
            DedupConfig(hash_ttl_days=31)


class TestDedupResult:
    """Tests for DedupResult model."""

    def test_not_duplicate_result(self):
        """Test creating a not-duplicate result."""
        result = DedupResult(is_duplicate=False)

        assert result.is_duplicate is False
        assert result.duplicate_of is None
        assert result.reason is None

    def test_duplicate_result(self):
        """Test creating a duplicate result."""
        result = DedupResult(
            is_duplicate=True,
            duplicate_of="original_hash",
            reason=DedupReason.EXACT_HASH,
        )

        assert result.is_duplicate is True
        assert result.duplicate_of == "original_hash"
        assert result.reason == DedupReason.EXACT_HASH


class TestDedupReason:
    """Tests for DedupReason enum."""

    def test_exact_hash_reason(self):
        """Test EXACT_HASH reason value."""
        assert DedupReason.EXACT_HASH.value == "exact_hash"

    def test_reason_is_string_enum(self):
        """Test that DedupReason is a string enum."""
        assert isinstance(DedupReason.EXACT_HASH, str)
        assert DedupReason.EXACT_HASH == "exact_hash"
