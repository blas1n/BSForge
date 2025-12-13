"""Topic deduplication service.

This module implements hash-based deduplication to prevent
processing the exact same content twice within a channel.

Uses Redis for fast hash lookups with configurable TTL.

Design Decision (Hash Only):
- Event overlap and semantic similarity were intentionally removed
- Same event from different sources provides diverse perspectives
- Persona should aggregate multiple sources for richer content
- Only exact duplicates (same content hash) are filtered
"""

from datetime import timedelta
from enum import Enum

from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis

from app.config import DedupConfig
from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class DedupReason(str, Enum):
    """Reason for duplicate detection."""

    EXACT_HASH = "exact_hash"


class DedupResult(BaseModel):
    """Result of duplicate detection.

    Attributes:
        is_duplicate: Whether the topic is a duplicate
        duplicate_of: Original topic hash if duplicate
        reason: Reason for duplicate detection
    """

    is_duplicate: bool
    duplicate_of: str | None = None
    reason: DedupReason | None = None


class TopicDeduplicator:
    """Detects and removes duplicate topics using hash matching.

    Only exact content matches are considered duplicates.
    Different articles about the same event are NOT duplicates
    - they provide diverse perspectives for the persona.

    Attributes:
        redis: Async Redis client (injected)
        config: Deduplication configuration
    """

    # Redis key prefix for hash storage
    HASH_KEY_PREFIX = "dedup:hash:"

    def __init__(
        self,
        redis: AsyncRedis,
        config: DedupConfig | None = None,
    ):
        """Initialize deduplicator.

        Args:
            redis: Async Redis client
            config: Deduplication configuration (uses defaults if not provided)
        """
        self.redis = redis
        self.config = config or DedupConfig()

    async def is_duplicate(self, topic: NormalizedTopic, channel_id: str) -> DedupResult:
        """Check if topic is a duplicate via hash match.

        Args:
            topic: Normalized topic to check
            channel_id: Channel ID for scoping

        Returns:
            DedupResult with duplicate status and details
        """
        hash_key = f"{self.HASH_KEY_PREFIX}{channel_id}:{topic.content_hash}"

        existing = await self.redis.get(hash_key)
        if existing:
            logger.info(
                "Duplicate detected (hash match)",
                title=topic.title_normalized[:50],
                hash=topic.content_hash[:16],
            )
            return DedupResult(
                is_duplicate=True,
                duplicate_of=topic.content_hash,
                reason=DedupReason.EXACT_HASH,
            )

        return DedupResult(is_duplicate=False)

    async def mark_as_seen(self, topic: NormalizedTopic, channel_id: str) -> None:
        """Mark topic as seen to prevent future duplicates.

        Stores hash in Redis with configurable TTL.

        Args:
            topic: Topic to mark
            channel_id: Channel ID
        """
        ttl_seconds = int(timedelta(days=self.config.hash_ttl_days).total_seconds())

        hash_key = f"{self.HASH_KEY_PREFIX}{channel_id}:{topic.content_hash}"
        await self.redis.setex(hash_key, ttl_seconds, topic.title_normalized)

        logger.debug(
            "Topic marked as seen",
            hash=topic.content_hash[:16],
            channel_id=channel_id,
            ttl_days=self.config.hash_ttl_days,
        )


__all__ = [
    "TopicDeduplicator",
    "DedupResult",
    "DedupReason",
]
