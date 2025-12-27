"""Topic queue manager service.

Manages priority queues for scored topics using Redis sorted sets.
Topics are prioritized by their total score, with higher scores
having higher priority (retrieved first).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.config import QueueConfig
from app.core.logging import get_logger
from app.services.collector.base import ScoredTopic

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class QueueStats(BaseModel):
    """Statistics for a channel's topic queue."""

    channel_id: uuid.UUID
    pending_count: int = 0
    highest_score: int | None = None
    lowest_score: int | None = None
    oldest_topic_age_hours: float | None = None


class TopicQueueManager:
    """Manages priority queues for scored topics.

    Uses Redis sorted sets for efficient priority queue operations.
    Each channel has its own queue, keyed by channel_id.

    Key structure:
    - topic_queue:{channel_id} - Sorted set with score as priority
    - topic_data:{channel_id}:{topic_hash} - Hash storing topic data

    Attributes:
        redis: Async Redis client (injected)
        config: Queue configuration
        key_prefix: Redis key prefix for queue
    """

    def __init__(
        self,
        redis: Redis[Any],
        config: QueueConfig | None = None,
    ):
        """Initialize queue manager.

        Args:
            redis: Async Redis client
            config: Queue configuration (uses defaults if not provided)
        """
        self.redis = redis
        self.config = config or QueueConfig()
        self.key_prefix = "topic_queue"
        self.data_prefix = "topic_data"

    def _queue_key(self, channel_id: uuid.UUID) -> str:
        """Get Redis key for channel's queue."""
        return f"{self.key_prefix}:{channel_id}"

    def _data_key(self, channel_id: uuid.UUID, content_hash: str) -> str:
        """Get Redis key for topic data."""
        return f"{self.data_prefix}:{channel_id}:{content_hash}"

    async def add_topic(
        self,
        channel_id: uuid.UUID,
        topic: ScoredTopic,
    ) -> bool:
        """Add a scored topic to the channel's priority queue.

        Topics are scored by their total_score (0-100).
        If queue is full, lowest scoring topics are removed.

        Args:
            channel_id: Channel UUID
            topic: Scored topic to add

        Returns:
            True if topic was added, False if rejected
        """
        # Check minimum score threshold
        if topic.score_total < self.config.min_score_threshold:
            logger.debug(
                "Topic rejected: below threshold",
                title=topic.title_normalized[:50],
                score=topic.score_total,
                threshold=self.config.min_score_threshold,
            )
            return False

        queue_key = self._queue_key(channel_id)

        # Check current queue size
        current_size = await self.redis.zcard(queue_key)

        if current_size >= self.config.max_pending_size:
            # Get lowest score in queue
            lowest = await self.redis.zrange(queue_key, 0, 0, withscores=True)
            if lowest:
                lowest_hash, lowest_score = lowest[0]
                if topic.score_total <= lowest_score:
                    logger.debug(
                        "Topic rejected: queue full, score not high enough",
                        title=topic.title_normalized[:50],
                        score=topic.score_total,
                        lowest_in_queue=lowest_score,
                    )
                    return False

                # Remove lowest scoring topic
                await self.redis.zrem(queue_key, lowest_hash)
                # Also remove its data
                lowest_data_key = self._data_key(
                    channel_id,
                    lowest_hash.decode() if isinstance(lowest_hash, bytes) else lowest_hash,
                )
                await self.redis.delete(lowest_data_key)
                logger.debug(
                    "Removed lowest scoring topic to make room",
                    removed_hash=lowest_hash,
                    removed_score=lowest_score,
                )

        # Serialize topic data
        topic_data = topic.model_dump_json()

        # Add to sorted set (score as priority)
        await self.redis.zadd(queue_key, {topic.content_hash: topic.score_total})

        # Store full topic data
        data_key = self._data_key(channel_id, topic.content_hash)
        ttl_seconds = self.config.auto_expire_hours * 3600
        await self.redis.setex(data_key, ttl_seconds, topic_data)

        logger.info(
            "Topic added to queue",
            channel_id=str(channel_id),
            title=topic.title_normalized[:50],
            score=topic.score_total,
            queue_size=(
                current_size + 1 if current_size < self.config.max_pending_size else current_size
            ),
        )

        return True

    async def get_next_topic(self, channel_id: uuid.UUID) -> ScoredTopic | None:
        """Get and remove the highest priority topic from queue.

        Args:
            channel_id: Channel UUID

        Returns:
            Highest scoring topic, or None if queue is empty
        """
        queue_key = self._queue_key(channel_id)

        # Get highest scoring topic (last element in sorted set)
        # ZPOPMAX returns [(member, score)]
        result = await self.redis.zpopmax(queue_key, count=1)

        if not result:
            return None

        content_hash, _ = result[0]
        if isinstance(content_hash, bytes):
            content_hash = content_hash.decode()

        # Get topic data
        data_key = self._data_key(channel_id, content_hash)
        topic_data = await self.redis.get(data_key)

        if not topic_data:
            logger.warning(
                "Topic data not found (expired?)",
                channel_id=str(channel_id),
                content_hash=content_hash,
            )
            return None

        # Delete data key since we're removing the topic
        await self.redis.delete(data_key)

        # Parse and return
        if isinstance(topic_data, bytes):
            topic_data = topic_data.decode()

        topic = ScoredTopic.model_validate_json(topic_data)

        logger.info(
            "Topic retrieved from queue",
            channel_id=str(channel_id),
            title=topic.title_normalized[:50],
            score=topic.score_total,
        )

        return topic

    async def peek_next_topic(self, channel_id: uuid.UUID) -> ScoredTopic | None:
        """Peek at the highest priority topic without removing it.

        Args:
            channel_id: Channel UUID

        Returns:
            Highest scoring topic, or None if queue is empty
        """
        queue_key = self._queue_key(channel_id)

        # Get highest scoring topic (last element)
        result = await self.redis.zrange(queue_key, -1, -1, withscores=True)

        if not result:
            return None

        content_hash, _ = result[0]
        if isinstance(content_hash, bytes):
            content_hash = content_hash.decode()

        # Get topic data
        data_key = self._data_key(channel_id, content_hash)
        topic_data = await self.redis.get(data_key)

        if not topic_data:
            return None

        if isinstance(topic_data, bytes):
            topic_data = topic_data.decode()

        return ScoredTopic.model_validate_json(topic_data)

    async def get_topics_batch(
        self,
        channel_id: uuid.UUID,
        count: int = 10,
        remove: bool = False,
    ) -> list[ScoredTopic]:
        """Get multiple topics from queue in priority order.

        Args:
            channel_id: Channel UUID
            count: Number of topics to retrieve
            remove: If True, remove topics from queue

        Returns:
            List of topics in descending score order
        """
        queue_key = self._queue_key(channel_id)

        if remove:
            # Pop multiple at once
            results = await self.redis.zpopmax(queue_key, count=count)
        else:
            # Just peek
            results = await self.redis.zrange(queue_key, -count, -1, withscores=True, desc=True)

        topics = []
        for content_hash, _ in results:
            if isinstance(content_hash, bytes):
                content_hash = content_hash.decode()

            data_key = self._data_key(channel_id, content_hash)
            topic_data = await self.redis.get(data_key)

            if topic_data:
                if isinstance(topic_data, bytes):
                    topic_data = topic_data.decode()

                topic = ScoredTopic.model_validate_json(topic_data)
                topics.append(topic)

                if remove:
                    await self.redis.delete(data_key)

        return topics

    async def remove_topic(
        self,
        channel_id: uuid.UUID,
        content_hash: str,
    ) -> bool:
        """Remove a specific topic from queue.

        Args:
            channel_id: Channel UUID
            content_hash: Topic's content hash

        Returns:
            True if topic was removed, False if not found
        """
        queue_key = self._queue_key(channel_id)

        removed = await self.redis.zrem(queue_key, content_hash)

        if removed:
            data_key = self._data_key(channel_id, content_hash)
            await self.redis.delete(data_key)
            logger.debug(
                "Topic removed from queue",
                channel_id=str(channel_id),
                content_hash=content_hash,
            )

        return bool(removed)

    async def get_queue_stats(self, channel_id: uuid.UUID) -> QueueStats:
        """Get statistics for a channel's queue.

        Args:
            channel_id: Channel UUID

        Returns:
            Queue statistics
        """
        queue_key = self._queue_key(channel_id)

        # Get count
        pending_count = await self.redis.zcard(queue_key)

        stats = QueueStats(
            channel_id=channel_id,
            pending_count=pending_count,
        )

        if pending_count > 0:
            # Get highest score
            highest = await self.redis.zrange(queue_key, -1, -1, withscores=True)
            if highest:
                stats.highest_score = int(highest[0][1])

            # Get lowest score
            lowest = await self.redis.zrange(queue_key, 0, 0, withscores=True)
            if lowest:
                stats.lowest_score = int(lowest[0][1])

        return stats

    async def clear_queue(self, channel_id: uuid.UUID) -> int:
        """Clear all topics from a channel's queue.

        Args:
            channel_id: Channel UUID

        Returns:
            Number of topics removed
        """
        queue_key = self._queue_key(channel_id)

        # Get all content hashes first
        all_hashes = await self.redis.zrange(queue_key, 0, -1)

        # Delete all data keys
        for content_hash in all_hashes:
            if isinstance(content_hash, bytes):
                content_hash = content_hash.decode()
            data_key = self._data_key(channel_id, content_hash)
            await self.redis.delete(data_key)

        # Delete the sorted set
        count = await self.redis.zcard(queue_key)
        await self.redis.delete(queue_key)

        logger.info(
            "Queue cleared",
            channel_id=str(channel_id),
            removed_count=count,
        )

        return count

    async def cleanup_expired(self, channel_id: uuid.UUID) -> int:
        """Remove topics whose data has expired.

        Since Redis handles TTL on data keys automatically,
        this cleans up orphaned entries in the sorted set.

        Args:
            channel_id: Channel UUID

        Returns:
            Number of orphaned entries removed
        """
        queue_key = self._queue_key(channel_id)

        # Get all content hashes
        all_hashes = await self.redis.zrange(queue_key, 0, -1)

        removed = 0
        for content_hash in all_hashes:
            if isinstance(content_hash, bytes):
                content_hash = content_hash.decode()

            # Check if data still exists
            data_key = self._data_key(channel_id, content_hash)
            exists = await self.redis.exists(data_key)

            if not exists:
                # Data expired, remove from sorted set
                await self.redis.zrem(queue_key, content_hash)
                removed += 1

        if removed > 0:
            logger.info(
                "Cleaned up expired topics",
                channel_id=str(channel_id),
                removed_count=removed,
            )

        return removed

    async def get_topics_by_score_range(
        self,
        channel_id: uuid.UUID,
        min_score: int = 0,
        max_score: int = 100,
    ) -> list[ScoredTopic]:
        """Get topics within a score range.

        Args:
            channel_id: Channel UUID
            min_score: Minimum score (inclusive)
            max_score: Maximum score (inclusive)

        Returns:
            List of topics in the score range
        """
        queue_key = self._queue_key(channel_id)

        # Get hashes in score range
        results = await self.redis.zrangebyscore(queue_key, min_score, max_score, withscores=True)

        topics = []
        for content_hash, _ in results:
            if isinstance(content_hash, bytes):
                content_hash = content_hash.decode()

            data_key = self._data_key(channel_id, content_hash)
            topic_data = await self.redis.get(data_key)

            if topic_data:
                if isinstance(topic_data, bytes):
                    topic_data = topic_data.decode()

                topic = ScoredTopic.model_validate_json(topic_data)
                topics.append(topic)

        return topics


__all__ = ["TopicQueueManager", "QueueConfig", "QueueStats"]
