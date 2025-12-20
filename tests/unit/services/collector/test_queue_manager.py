"""Unit tests for TopicQueueManager.

Tests cover:
- Adding topics to queue
- Score threshold filtering
- Queue size limits
- Priority ordering (highest score first)
- Batch operations
- Queue statistics
- Cleanup of expired topics
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.services.collector.base import ScoredTopic
from app.services.collector.queue_manager import (
    QueueConfig,
    TopicQueueManager,
)


def create_scored_topic(
    score: int = 50,
    title: str = "Test Topic",
    content_hash: str | None = None,
) -> ScoredTopic:
    """Create a test ScoredTopic."""
    return ScoredTopic(
        source_id=uuid.uuid4(),
        source_url=HttpUrl("https://example.com/topic"),
        title_original=title,
        title_normalized=title.lower(),
        summary=f"Summary of {title}",
        terms=["tech", "test", "topic"],
        entities={},
        language="en",
        published_at=datetime.now(UTC),
        content_hash=content_hash or f"hash_{score}_{uuid.uuid4().hex[:8]}",
        metrics={"normalized_score": 0.5},
        score_source=0.5,
        score_freshness=0.8,
        score_trend=0.3,
        score_relevance=0.5,
        score_total=score,
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client."""
    mock = AsyncMock()

    # Default behaviors
    mock.zcard.return_value = 0
    mock.zadd.return_value = 1
    mock.setex.return_value = True
    mock.get.return_value = None
    mock.delete.return_value = 1
    mock.zrem.return_value = 1
    mock.exists.return_value = True

    return mock


@pytest.fixture
def queue_manager(mock_redis: AsyncMock) -> TopicQueueManager:
    """Create a TopicQueueManager with mock Redis."""
    return TopicQueueManager(
        redis=mock_redis,
        config=QueueConfig(
            max_pending_size=10,
            min_score_threshold=30,
            auto_expire_hours=72,
        ),
    )


class TestAddTopic:
    """Tests for adding topics to queue."""

    @pytest.mark.asyncio
    async def test_add_topic_success(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test successfully adding a topic."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=50)

        result = await queue_manager.add_topic(channel_id, topic)

        assert result is True
        mock_redis.zadd.assert_called_once()
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_topic_below_threshold(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test rejecting topic below score threshold."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=20)  # Below 30 threshold

        result = await queue_manager.add_topic(channel_id, topic)

        assert result is False
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_topic_queue_full_higher_score(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test adding topic to full queue with higher score."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=80)

        mock_redis.zcard.return_value = 10  # Queue is full
        mock_redis.zrange.return_value = [(b"old_hash", 40)]  # Lowest has score 40

        result = await queue_manager.add_topic(channel_id, topic)

        assert result is True
        # Should remove lowest scoring topic
        mock_redis.zrem.assert_called()

    @pytest.mark.asyncio
    async def test_add_topic_queue_full_lower_score(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test rejecting topic when queue full and score not high enough."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=35)  # Just above threshold

        mock_redis.zcard.return_value = 10  # Queue is full
        mock_redis.zrange.return_value = [(b"existing_hash", 40)]  # Lowest has score 40

        result = await queue_manager.add_topic(channel_id, topic)

        assert result is False


class TestGetNextTopic:
    """Tests for retrieving topics from queue."""

    @pytest.mark.asyncio
    async def test_get_next_topic_success(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting highest priority topic."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=70)

        mock_redis.zpopmax.return_value = [(topic.content_hash.encode(), 70)]
        mock_redis.get.return_value = topic.model_dump_json().encode()

        result = await queue_manager.get_next_topic(channel_id)

        assert result is not None
        assert result.score_total == 70
        mock_redis.delete.assert_called_once()  # Data key should be deleted

    @pytest.mark.asyncio
    async def test_get_next_topic_empty_queue(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting topic from empty queue."""
        channel_id = uuid.uuid4()
        mock_redis.zpopmax.return_value = []

        result = await queue_manager.get_next_topic(channel_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_topic_expired_data(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test handling expired topic data."""
        channel_id = uuid.uuid4()
        mock_redis.zpopmax.return_value = [(b"expired_hash", 50)]
        mock_redis.get.return_value = None  # Data expired

        result = await queue_manager.get_next_topic(channel_id)

        assert result is None


class TestPeekNextTopic:
    """Tests for peeking at topics without removal."""

    @pytest.mark.asyncio
    async def test_peek_next_topic(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test peeking at highest priority topic."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=60)

        mock_redis.zrange.return_value = [(topic.content_hash.encode(), 60)]
        mock_redis.get.return_value = topic.model_dump_json().encode()

        result = await queue_manager.peek_next_topic(channel_id)

        assert result is not None
        assert result.score_total == 60
        mock_redis.delete.assert_not_called()  # Should NOT delete


class TestBatchOperations:
    """Tests for batch topic operations."""

    @pytest.mark.asyncio
    async def test_get_topics_batch(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting multiple topics."""
        channel_id = uuid.uuid4()
        topics = [
            create_scored_topic(score=80, content_hash="hash1"),
            create_scored_topic(score=70, content_hash="hash2"),
        ]

        mock_redis.zrange.return_value = [
            (b"hash1", 80),
            (b"hash2", 70),
        ]

        # Setup mock to return different data for each hash
        async def mock_get(key: str) -> bytes | None:
            if "hash1" in key:
                return topics[0].model_dump_json().encode()
            if "hash2" in key:
                return topics[1].model_dump_json().encode()
            return None

        mock_redis.get.side_effect = mock_get

        result = await queue_manager.get_topics_batch(channel_id, count=5)

        assert len(result) == 2
        assert result[0].score_total == 80
        assert result[1].score_total == 70


class TestQueueStats:
    """Tests for queue statistics."""

    @pytest.mark.asyncio
    async def test_get_queue_stats(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting queue statistics."""
        channel_id = uuid.uuid4()

        mock_redis.zcard.return_value = 5
        mock_redis.zrange.side_effect = [
            [(b"highest", 90)],  # Highest score query
            [(b"lowest", 40)],  # Lowest score query
        ]

        stats = await queue_manager.get_queue_stats(channel_id)

        assert stats.pending_count == 5
        assert stats.highest_score == 90
        assert stats.lowest_score == 40

    @pytest.mark.asyncio
    async def test_get_queue_stats_empty(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting stats for empty queue."""
        channel_id = uuid.uuid4()
        mock_redis.zcard.return_value = 0

        stats = await queue_manager.get_queue_stats(channel_id)

        assert stats.pending_count == 0
        assert stats.highest_score is None
        assert stats.lowest_score is None


class TestClearQueue:
    """Tests for clearing queues."""

    @pytest.mark.asyncio
    async def test_clear_queue(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test clearing all topics from queue."""
        channel_id = uuid.uuid4()

        mock_redis.zrange.return_value = [b"hash1", b"hash2", b"hash3"]
        mock_redis.zcard.return_value = 3

        count = await queue_manager.clear_queue(channel_id)

        assert count == 3
        # Should delete all data keys + the sorted set
        assert mock_redis.delete.call_count == 4


class TestCleanupExpired:
    """Tests for cleaning up expired topics."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_topics(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test removing topics with expired data."""
        channel_id = uuid.uuid4()

        mock_redis.zrange.return_value = [b"valid_hash", b"expired_hash"]

        # First hash exists, second doesn't
        async def mock_exists(key: str) -> bool:
            return "valid_hash" in str(key)

        mock_redis.exists.side_effect = mock_exists

        removed = await queue_manager.cleanup_expired(channel_id)

        assert removed == 1
        mock_redis.zrem.assert_called_once()


class TestRemoveTopic:
    """Tests for removing specific topics."""

    @pytest.mark.asyncio
    async def test_remove_topic_exists(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test removing existing topic."""
        channel_id = uuid.uuid4()
        mock_redis.zrem.return_value = 1

        result = await queue_manager.remove_topic(channel_id, "test_hash")

        assert result is True
        mock_redis.zrem.assert_called_once()
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_topic_not_found(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test removing non-existent topic."""
        channel_id = uuid.uuid4()
        mock_redis.zrem.return_value = 0

        result = await queue_manager.remove_topic(channel_id, "nonexistent")

        assert result is False


class TestScoreRangeQuery:
    """Tests for score range queries."""

    @pytest.mark.asyncio
    async def test_get_topics_by_score_range(
        self, queue_manager: TopicQueueManager, mock_redis: AsyncMock
    ) -> None:
        """Test getting topics within score range."""
        channel_id = uuid.uuid4()
        topic = create_scored_topic(score=75, content_hash="hash75")

        mock_redis.zrangebyscore.return_value = [(b"hash75", 75)]
        mock_redis.get.return_value = topic.model_dump_json().encode()

        result = await queue_manager.get_topics_by_score_range(
            channel_id, min_score=70, max_score=80
        )

        assert len(result) == 1
        assert result[0].score_total == 75


class TestQueueConfig:
    """Tests for QueueConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = QueueConfig()

        assert config.max_pending_size == 100
        assert config.min_score_threshold == 30
        assert config.auto_expire_hours == 72

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = QueueConfig(
            max_pending_size=50,
            min_score_threshold=40,
            auto_expire_hours=48,
        )

        assert config.max_pending_size == 50
        assert config.min_score_threshold == 40
        assert config.auto_expire_hours == 48
