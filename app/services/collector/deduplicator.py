"""Topic deduplication service.

This module implements 3-level deduplication:
1. Hash exact match (Redis, <1ms)
2. Title similarity (Vector search, ~100ms) - placeholder for now
3. Event detection (Entity overlap, ~50ms)

Uses Redis for fast hash lookups with 7-day rolling window.
"""

from datetime import timedelta

from app.core.logging import get_logger
from app.core.redis import async_redis_client
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class TopicDeduplicator:
    """Detects and removes duplicate topics.

    Uses multi-level approach:
    - Level 1: Exact hash match (fastest)
    - Level 2: Semantic similarity (future: vector search)
    - Level 3: Event clustering (entity overlap)
    """

    def __init__(self, redis_ttl_days: int = 7):
        """Initialize deduplicator.

        Args:
            redis_ttl_days: Days to keep hashes in Redis cache
        """
        self.redis = async_redis_client
        self.redis_ttl = timedelta(days=redis_ttl_days)
        self.hash_key_prefix = "topic:hash:"

    async def is_duplicate(
        self, topic: NormalizedTopic, channel_id: str
    ) -> tuple[bool, str | None]:
        """Check if topic is a duplicate.

        Args:
            topic: Normalized topic to check
            channel_id: Channel ID for scoping

        Returns:
            Tuple of (is_duplicate, reason)
            reason is None if not duplicate
        """
        # Level 1: Hash exact match
        is_dup, reason = await self._check_hash_match(topic, channel_id)
        if is_dup:
            return True, reason

        # Level 2: Semantic similarity (placeholder for future implementation)
        # TODO: Implement vector similarity search when Chroma/Pinecone is set up

        # Level 3: Event clustering
        is_dup, reason = await self._check_event_overlap(topic, channel_id)
        if is_dup:
            return True, reason

        return False, None

    async def mark_as_seen(self, topic: NormalizedTopic, channel_id: str) -> None:
        """Mark topic as seen to prevent future duplicates.

        Args:
            topic: Topic to mark
            channel_id: Channel ID
        """
        # Store hash in Redis with TTL
        hash_key = f"{self.hash_key_prefix}{channel_id}:{topic.content_hash}"
        ttl_seconds = int(self.redis_ttl.total_seconds())

        await self.redis.setex(
            hash_key,
            ttl_seconds,
            topic.title_normalized,  # Store title for debugging
        )

        logger.debug(
            "Topic marked as seen",
            hash=topic.content_hash[:16],
            channel_id=channel_id,
            ttl_days=self.redis_ttl.days,
        )

    async def _check_hash_match(
        self, topic: NormalizedTopic, channel_id: str
    ) -> tuple[bool, str | None]:
        """Check for exact hash match in Redis.

        Args:
            topic: Topic to check
            channel_id: Channel ID

        Returns:
            Tuple of (is_duplicate, reason)
        """
        hash_key = f"{self.hash_key_prefix}{channel_id}:{topic.content_hash}"

        existing = await self.redis.get(hash_key)
        if existing:
            logger.info(
                "Duplicate detected (hash match)",
                title=topic.title_normalized[:50],
                existing_title=existing[:50] if existing else None,
                hash=topic.content_hash[:16],
            )
            return True, f"Exact duplicate (hash: {topic.content_hash[:16]})"

        return False, None

    async def _check_event_overlap(
        self, topic: NormalizedTopic, channel_id: str
    ) -> tuple[bool, str | None]:
        """Check for same event via entity overlap.

        Detects when different sources report the same event
        with different titles but overlapping entities.

        Args:
            topic: Topic to check
            channel_id: Channel ID

        Returns:
            Tuple of (is_duplicate, reason)
        """
        # Skip if no entities
        if not topic.entities or not any(topic.entities.values()):
            return False, None

        # Get all entity names
        all_entities = set()
        for entity_list in topic.entities.values():
            all_entities.update(entity_list)

        if len(all_entities) < 2:
            # Not enough entities to reliably detect events
            return False, None

        # TODO: Implement entity overlap detection
        # This requires storing recent topics' entities in Redis
        # For now, just log that we would check
        logger.debug(
            "Event overlap check skipped (not implemented)",
            entities=list(all_entities)[:5],
            entity_count=len(all_entities),
        )

        return False, None


__all__ = ["TopicDeduplicator"]
