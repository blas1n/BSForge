"""Topic collection pipeline service.

This module provides a unified service for collecting, normalizing, filtering,
and scoring topics for a channel. Used by both Celery workers and CLI scripts.

The pipeline:
1. Collect raw topics from sources (global pool + scoped sources)
2. Normalize (translate, classify, extract terms)
3. Filter (include/exclude terms)
4. Deduplicate (hash-based)
5. Score (multi-factor scoring)
6. Save to database

Usage:
    pipeline = TopicCollectionPipeline(session, redis)
    result = await pipeline.collect_for_channel(channel, config)
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DedupConfig, FilteringConfig, ScoringConfig
from app.config.sources import (
    HackerNewsConfig,
    RedditConfig,
)
from app.core.config_loader import load_defaults
from app.core.logging import get_logger
from app.models.channel import Channel
from app.models.topic import Topic, TopicStatus
from app.services.collector.base import NormalizedTopic, RawTopic, ScoredTopic
from app.services.collector.deduplicator import TopicDeduplicator
from app.services.collector.filter import TopicFilter
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.scorer import TopicScorer
from app.services.collector.sources.hackernews import HackerNewsSource
from app.services.collector.sources.reddit import RedditSource

logger = get_logger(__name__)


class CollectionStats(BaseModel):
    """Statistics from topic collection pipeline.

    Attributes:
        global_topics: Topics pulled from global pool
        scoped_topics: Topics collected from scoped sources
        total_collected: Total raw topics
        normalized_count: Topics after normalization
        filtered_count: Topics after filtering
        deduplicated_count: Topics after deduplication
        saved_count: Topics saved to database
        errors: List of error messages
    """

    global_topics: int = 0
    scoped_topics: int = 0
    total_collected: int = 0
    normalized_count: int = 0
    filtered_count: int = 0
    deduplicated_count: int = 0
    saved_count: int = 0
    errors: list[str] = []


def _get_collector_defaults() -> dict[str, Any]:
    """Get collector defaults from config/defaults.yaml."""
    defaults = load_defaults()
    collector = defaults.get("collector", {})
    return collector if isinstance(collector, dict) else {}


@dataclass
class CollectionConfig:
    """Configuration for topic collection.

    Attributes:
        enabled_sources: List of enabled source types (required from channel config)
        target_language: Target language for translation (required from channel config)
        source_overrides: Per-source configuration overrides
        include: Terms to include
        exclude: Terms to exclude
        max_topics: Maximum topics to process
        save_to_db: Whether to save topics to database
    """

    enabled_sources: list[str]  # Required - from channel config
    target_language: str  # Required - from channel config
    source_overrides: dict[str, Any] = field(default_factory=dict)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_topics: int = field(default_factory=lambda: _get_collector_defaults().get("max_topics", 20))
    save_to_db: bool = True

    @classmethod
    def from_channel_config(cls, channel_config: dict[str, Any]) -> "CollectionConfig":
        """Create CollectionConfig from channel YAML config.

        Args:
            channel_config: Channel configuration dictionary

        Returns:
            CollectionConfig instance

        Raises:
            ValueError: If required fields are missing from channel config
        """
        defaults = _get_collector_defaults()
        topic_collection = channel_config.get("topic_collection", {})
        filtering = channel_config.get("filtering", {})

        enabled_sources = topic_collection.get("enabled_sources")
        if not enabled_sources:
            raise ValueError("enabled_sources is required in channel config")

        target_language = topic_collection.get("target_language", "ko")

        return cls(
            enabled_sources=enabled_sources,
            target_language=target_language,
            source_overrides=topic_collection.get("source_overrides", {}),
            include=filtering.get("include", []),
            exclude=filtering.get("exclude", []),
            max_topics=defaults.get("max_topics", 20),
            save_to_db=True,
        )


class TopicCollectionPipeline:
    """Unified topic collection pipeline service.

    This service handles the full topic collection pipeline:
    1. Collect from sources (global pool + direct collection)
    2. Normalize (translate, classify)
    3. Filter (include/exclude terms)
    4. Deduplicate
    5. Score
    6. Save to DB

    Used by both Celery workers and CLI scripts to avoid code duplication.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis: AsyncRedis[bytes] | None = None,
        normalizer: TopicNormalizer | None = None,
        deduplicator: TopicDeduplicator | None = None,
        scorer: TopicScorer | None = None,
    ):
        """Initialize pipeline.

        Args:
            session: Database session
            redis: Redis client (optional, for deduplication and global pool)
            normalizer: Topic normalizer (uses default if None)
            deduplicator: Topic deduplicator (uses default if None)
            scorer: Topic scorer (uses default if None)
        """
        self.session = session
        self.redis = redis
        self.normalizer = normalizer or TopicNormalizer()
        self.scorer = scorer or TopicScorer(config=ScoringConfig())
        self.deduplicator: TopicDeduplicator | None

        if redis and deduplicator is None:
            self.deduplicator = TopicDeduplicator(redis=redis, config=DedupConfig())
        else:
            self.deduplicator = deduplicator

    async def collect_for_channel(
        self,
        channel: Channel,
        config: CollectionConfig,
    ) -> tuple[list[Topic], CollectionStats]:
        """Run full collection pipeline for a channel.

        Args:
            channel: Channel model
            config: Collection configuration

        Returns:
            Tuple of (saved topics, collection stats)
        """
        stats = CollectionStats()
        logger.info(f"Starting collection for channel: {channel.name}")

        # Step 1: Collect raw topics
        raw_topics = await self._collect_raw_topics(config, stats)

        if not raw_topics:
            logger.warning(f"No raw topics collected for {channel.name}")
            return [], stats

        stats.total_collected = len(raw_topics)
        logger.info(f"Collected {len(raw_topics)} raw topics")

        # Step 2: Normalize topics
        normalized = await self._normalize_topics(raw_topics, config.target_language, stats)

        if not normalized:
            logger.warning(f"No topics after normalization for {channel.name}")
            return [], stats

        stats.normalized_count = len(normalized)
        logger.info(f"Normalized {len(normalized)} topics")

        # Step 3: Filter topics
        filtered = self._filter_topics(normalized, config)

        if not filtered:
            logger.warning(f"No topics after filtering for {channel.name}")
            return [], stats

        stats.filtered_count = len(filtered)
        logger.info(f"Filtered to {len(filtered)} topics")

        # Step 4: Deduplicate
        deduplicated = await self._deduplicate_topics(filtered, str(channel.id), stats)

        stats.deduplicated_count = len(deduplicated)
        logger.info(f"Deduplicated to {len(deduplicated)} topics")

        # Step 5: Score topics
        scored = self._score_topics(deduplicated, stats)

        # Sort by score (x[2] is ScoredTopic)
        scored.sort(key=lambda x: x[2].score_total, reverse=True)

        # Step 6: Save to DB
        if config.save_to_db:
            saved_topics = await self._save_topics_to_db(channel, scored)
            stats.saved_count = len(saved_topics)
            logger.info(f"Saved {len(saved_topics)} topics to DB")
            return saved_topics, stats

        # Return as Topic models without saving
        topics = [self._create_topic_model(channel, raw, norm, sc) for raw, norm, sc in scored]
        return topics, stats

    async def _collect_raw_topics(
        self,
        config: CollectionConfig,
        stats: CollectionStats,
    ) -> list[RawTopic]:
        """Collect raw topics from all configured sources.

        Args:
            config: Collection configuration
            stats: Stats to update

        Returns:
            List of raw topics
        """
        all_topics: list[RawTopic] = []
        defaults = _get_collector_defaults()
        source_defaults = defaults.get("sources", {})

        # Collect from HackerNews
        if "hackernews" in config.enabled_sources:
            logger.info("Collecting from HackerNews...")
            try:
                hn_defaults = source_defaults.get("hackernews", {})
                overrides = config.source_overrides.get("hackernews", {})
                min_score = overrides.get("filters", {}).get(
                    "min_score", hn_defaults.get("min_score", 30)
                )
                limit = overrides.get("limit", hn_defaults.get("limit", 30))

                hn_config = HackerNewsConfig(limit=limit, min_score=min_score)
                hn_source = HackerNewsSource(config=hn_config, source_id=uuid.uuid4())
                hn_topics = await hn_source.collect()

                logger.info(f"HackerNews: {len(hn_topics)} topics")
                all_topics.extend(hn_topics)
                stats.global_topics += len(hn_topics)
            except Exception as e:
                error_msg = f"HackerNews collection failed: {e}"
                logger.error(error_msg, exc_info=True)
                stats.errors.append(error_msg)

        # Collect from Reddit
        if "reddit" in config.enabled_sources:
            logger.info("Collecting from Reddit...")
            try:
                reddit_defaults = source_defaults.get("reddit", {})
                overrides = config.source_overrides.get("reddit", {})
                subreddits = overrides.get("params", {}).get("subreddits")
                if not subreddits:
                    raise ValueError(
                        "reddit.params.subreddits is required in channel config "
                        "when reddit is in enabled_sources"
                    )
                min_score = overrides.get("filters", {}).get(
                    "min_score", reddit_defaults.get("min_score", 30)
                )
                limit = overrides.get("limit", reddit_defaults.get("limit", 20))

                reddit_config = RedditConfig(
                    subreddits=subreddits, limit=limit, min_score=min_score
                )
                reddit_source = RedditSource(config=reddit_config, source_id=uuid.uuid4())
                reddit_topics = await reddit_source.collect()

                logger.info(f"Reddit: {len(reddit_topics)} topics")
                all_topics.extend(reddit_topics)
                stats.scoped_topics += len(reddit_topics)
            except Exception as e:
                error_msg = f"Reddit collection failed: {e}"
                logger.error(error_msg, exc_info=True)
                stats.errors.append(error_msg)

        # Limit topics
        return all_topics[: config.max_topics]

    async def _normalize_topics(
        self,
        raw_topics: list[RawTopic],
        target_language: str,
        stats: CollectionStats,
    ) -> list[tuple[RawTopic, NormalizedTopic]]:
        """Normalize raw topics.

        Args:
            raw_topics: List of raw topics
            target_language: Target language for translation
            stats: Stats to update

        Returns:
            List of (raw, normalized) tuples
        """
        normalized: list[tuple[RawTopic, NormalizedTopic]] = []
        demo_source_id = uuid.uuid4()

        for raw in raw_topics:
            try:
                norm = await self.normalizer.normalize(
                    raw, source_id=demo_source_id, target_language=target_language
                )
                normalized.append((raw, norm))
            except Exception as e:
                error_msg = f"Normalization failed for '{raw.title[:30]}...': {e}"
                logger.warning(error_msg)
                stats.errors.append(error_msg)

        return normalized

    def _filter_topics(
        self,
        normalized: list[tuple[RawTopic, NormalizedTopic]],
        config: CollectionConfig,
    ) -> list[tuple[RawTopic, NormalizedTopic]]:
        """Filter topics by terms.

        Args:
            normalized: List of (raw, normalized) tuples
            config: Collection configuration

        Returns:
            Filtered list of (raw, normalized) tuples
        """
        if not config.include and not config.exclude:
            return normalized

        filter_config = FilteringConfig(
            include=config.include,
            exclude=config.exclude,
        )
        topic_filter = TopicFilter(filter_config)

        filtered = []
        for raw, norm in normalized:
            result = topic_filter.filter(norm)
            if result.passed:
                filtered.append((raw, norm))

        return filtered

    async def _deduplicate_topics(
        self,
        topics: list[tuple[RawTopic, NormalizedTopic]],
        channel_id: str,
        stats: CollectionStats,
    ) -> list[tuple[RawTopic, NormalizedTopic]]:
        """Remove duplicate topics.

        Args:
            topics: List of (raw, normalized) tuples
            channel_id: Channel ID for scoped deduplication
            stats: Stats to update

        Returns:
            Deduplicated list
        """
        if not self.deduplicator:
            return topics

        deduplicated = []
        for raw, norm in topics:
            try:
                result = await self.deduplicator.is_duplicate(norm, channel_id)
                if not result.is_duplicate:
                    deduplicated.append((raw, norm))
                    await self.deduplicator.mark_as_seen(norm, channel_id)
            except Exception as e:
                error_msg = f"Deduplication error: {e}"
                logger.warning(error_msg)
                stats.errors.append(error_msg)
                # Include topic on error
                deduplicated.append((raw, norm))

        return deduplicated

    def _score_topics(
        self,
        topics: list[tuple[RawTopic, NormalizedTopic]],
        stats: CollectionStats,
    ) -> list[tuple[RawTopic, NormalizedTopic, ScoredTopic]]:
        """Score topics.

        Args:
            topics: List of (raw, normalized) tuples
            stats: Stats to update

        Returns:
            List of (raw, normalized, scored) tuples
        """
        scored = []
        for raw, norm in topics:
            try:
                sc = self.scorer.score(norm)
                scored.append((raw, norm, sc))
            except Exception as e:
                error_msg = f"Scoring failed for '{norm.title_normalized[:30]}...': {e}"
                logger.warning(error_msg)
                stats.errors.append(error_msg)

        return scored

    async def _save_topics_to_db(
        self,
        channel: Channel,
        scored_topics: list[tuple[RawTopic, NormalizedTopic, ScoredTopic]],
    ) -> list[Topic]:
        """Save scored topics to database.

        Args:
            channel: Channel model
            scored_topics: List of (raw, normalized, scored) tuples

        Returns:
            List of saved Topic models
        """
        saved: list[Topic] = []
        defaults = _get_collector_defaults()
        top_topics_to_save = defaults.get("top_topics_to_save", 5)

        for raw, norm, sc in scored_topics[:top_topics_to_save]:
            # Check for existing topic
            content_hash = hashlib.sha256(
                (norm.title_normalized + str(norm.source_url)).encode()
            ).hexdigest()

            result = await self.session.execute(
                select(Topic).where(
                    Topic.channel_id == channel.id,
                    Topic.content_hash == content_hash,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.debug(f"Skipping duplicate: {norm.title_normalized[:40]}...")
                continue

            topic = self._create_topic_model(channel, raw, norm, sc, content_hash)
            self.session.add(topic)
            saved.append(topic)

            logger.info(
                f"Saved topic: {topic.title_normalized[:40]}... (score: {topic.score_total})"
            )

        await self.session.commit()
        return saved

    def _create_topic_model(
        self,
        channel: Channel,
        raw: RawTopic,
        norm: NormalizedTopic,
        scored: ScoredTopic,
        content_hash: str | None = None,
    ) -> Topic:
        """Create Topic model from processed data.

        Args:
            channel: Channel model
            raw: Raw topic
            norm: Normalized topic
            scored: Scored topic
            content_hash: Pre-computed hash (optional)

        Returns:
            Topic model (not yet saved)
        """
        if content_hash is None:
            content_hash = hashlib.sha256(
                (norm.title_normalized + str(norm.source_url)).encode()
            ).hexdigest()

        return Topic(
            id=uuid.uuid4(),
            channel_id=channel.id,
            source_id=None,
            title_original=raw.title,
            title_translated=norm.title_translated,
            title_normalized=norm.title_normalized,
            summary=norm.summary or (raw.content[:200] if raw.content else ""),
            source_url=str(norm.source_url),
            terms=norm.terms or [],
            entities={},
            language=norm.language or "en",
            score_source=scored.score_source,
            score_freshness=scored.score_freshness,
            score_trend=scored.score_trend,
            score_relevance=scored.score_relevance,
            score_total=scored.score_total,
            status=TopicStatus.APPROVED,
            published_at=norm.published_at,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            content_hash=content_hash,
        )


__all__ = [
    "TopicCollectionPipeline",
    "CollectionConfig",
    "CollectionStats",
]
