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

from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FilteringConfig

if TYPE_CHECKING:
    from redis.asyncio import Redis

from app.core.config_loader import load_defaults
from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.models.channel import Channel
from app.models.topic import Topic, TopicStatus
from app.services.collector.base import NormalizedTopic, RawTopic, ScoredTopic
from app.services.collector.deduplicator import TopicDeduplicator
from app.services.collector.filter import TopicFilter
from app.services.collector.global_pool import (
    GlobalTopicPool,
    ScopedSourceCache,
    is_global_source,
)
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.scorer import TopicScorer
from app.services.collector.sources.factory import create_source

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
        global_sources: List of global source types (hackernews, google_trends, youtube_trending)
        scoped_sources: List of scoped source types (reddit, dcinside, etc.)
        target_language: Target language for translation (required from channel config)
        source_overrides: Per-source configuration overrides
        include: Terms to include
        exclude: Terms to exclude
        max_topics: Maximum topics to process
        save_to_db: Whether to save topics to database
    """

    global_sources: list[str]  # Global sources (shared across channels)
    scoped_sources: list[str]  # Scoped sources (channel-specific params)
    target_language: str  # Required - from channel config
    source_overrides: dict[str, Any] = field(default_factory=dict)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_topics: int = field(default_factory=lambda: _get_collector_defaults().get("max_topics", 20))
    save_to_db: bool = True

    @property
    def enabled_sources(self) -> list[str]:
        """All enabled sources (global + scoped) for backward compatibility."""
        return self.global_sources + self.scoped_sources

    @classmethod
    def from_channel_config(cls, channel_config: dict[str, Any]) -> CollectionConfig:
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

        global_sources = topic_collection.get("global_sources", [])
        scoped_sources = topic_collection.get("scoped_sources", [])
        target_language = topic_collection.get("target_language", "ko")

        return cls(
            global_sources=global_sources,
            scoped_sources=scoped_sources,
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
    1. Collect from sources (global pool + scoped sources via factory)
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
        http_client: HTTPClient,
        normalizer: TopicNormalizer,
        redis: Redis[Any],
        deduplicator: TopicDeduplicator,
        scorer: TopicScorer,
        global_pool: GlobalTopicPool,
        scoped_cache: ScopedSourceCache,
    ):
        """Initialize pipeline.

        Args:
            session: Database session
            http_client: HTTP client for source requests
            normalizer: Topic normalizer
            redis: Redis client for caching
            deduplicator: Topic deduplicator
            scorer: Topic scorer
            global_pool: Global topic pool for shared sources
            scoped_cache: Scoped source cache
        """
        self.session = session
        self.http_client = http_client
        self.normalizer = normalizer
        self.redis = redis
        self.deduplicator = deduplicator
        self.scorer = scorer
        self.global_pool = global_pool
        self.scoped_cache = scoped_cache

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
        scored = self._score_topics(deduplicated, stats, config)

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

        Uses GlobalTopicPool for global sources (HN, Trends, YouTube) and
        ScopedSourceCache for scoped sources (Reddit, DCInside, etc.).
        Falls back to direct collection if Redis is not available.

        Balanced sampling: Takes proportional topics from each source to ensure
        all sources are represented in the final result.

        Args:
            config: Collection configuration
            stats: Stats to update

        Returns:
            List of raw topics
        """
        # Collect all topics grouped by source
        topics_by_source: dict[str, list[RawTopic]] = {}

        for source_name in config.enabled_sources:
            try:
                if is_global_source(source_name):
                    # Global source: try pool first, then direct collection
                    topics = await self._collect_from_global_source(
                        source_name, config.source_overrides.get(source_name, {}), stats
                    )
                else:
                    # Scoped source: use cache or direct collection
                    topics = await self._collect_from_scoped_source(
                        source_name, config.source_overrides.get(source_name, {}), stats
                    )

                if topics:
                    topics_by_source[source_name] = topics

            except Exception as e:
                error_msg = f"{source_name} collection failed: {e}"
                logger.error(error_msg, exc_info=True)
                stats.errors.append(error_msg)

        # Balanced sampling: proportionally sample from each source
        return self._balanced_sample(topics_by_source, config.max_topics)

    def _balanced_sample(
        self,
        topics_by_source: dict[str, list[RawTopic]],
        max_topics: int,
    ) -> list[RawTopic]:
        """Sample topics proportionally from each source.

        Ensures all sources are represented in the result by taking
        a proportional number of topics from each source.

        Args:
            topics_by_source: Topics grouped by source name
            max_topics: Maximum total topics to return

        Returns:
            Balanced list of topics from all sources
        """
        if not topics_by_source:
            return []

        total_topics = sum(len(topics) for topics in topics_by_source.values())
        if total_topics <= max_topics:
            # Return all if under limit
            all_topics = []
            for topics in topics_by_source.values():
                all_topics.extend(topics)
            return all_topics

        # Calculate proportional allocation for each source
        num_sources = len(topics_by_source)
        base_per_source = max_topics // num_sources
        remainder = max_topics % num_sources

        result: list[RawTopic] = []
        sources_sorted = sorted(
            topics_by_source.keys(),
            key=lambda s: len(topics_by_source[s]),
            reverse=True,
        )

        for i, source_name in enumerate(sources_sorted):
            topics = topics_by_source[source_name]
            # Give extra 1 topic to first 'remainder' sources
            allocation = base_per_source + (1 if i < remainder else 0)
            # Take up to allocation, but not more than available
            take = min(allocation, len(topics))
            # Shuffle and take top N to get variety
            shuffled = list(topics)
            random.shuffle(shuffled)
            result.extend(shuffled[:take])

        logger.info(
            "Balanced sampling complete",
            total_sources=num_sources,
            total_available=total_topics,
            sampled=len(result),
        )
        return result

    async def _collect_from_global_source(
        self,
        source_name: str,
        overrides: dict[str, Any],
        stats: CollectionStats,
    ) -> list[RawTopic]:
        """Collect from a global source, using pool if available.

        Args:
            source_name: Name of the source
            overrides: Source-specific overrides
            stats: Stats to update

        Returns:
            List of raw topics
        """
        # Try global pool first
        if self.global_pool:
            pool_topics = await self.global_pool.get_topics(source_name)
            if pool_topics:
                logger.info(f"Got {len(pool_topics)} topics from global pool: {source_name}")
                stats.global_topics += len(pool_topics)
                return pool_topics

        # Pool empty or unavailable, collect directly
        logger.info(f"Collecting directly from global source: {source_name}")
        topics = await self._collect_directly(source_name, overrides)

        # Store in pool for future use
        if self.global_pool and topics:
            await self.global_pool.add_topics(source_name, topics)

        stats.global_topics += len(topics)
        logger.info(f"{source_name}: {len(topics)} topics")
        return topics

    async def _collect_from_scoped_source(
        self,
        source_name: str,
        overrides: dict[str, Any],
        stats: CollectionStats,
    ) -> list[RawTopic]:
        """Collect from a scoped source, using cache if available.

        Args:
            source_name: Name of the source
            overrides: Source-specific overrides
            stats: Stats to update

        Returns:
            List of raw topics
        """
        params = overrides.get("params", {})

        # Try scoped cache first
        if self.scoped_cache and params:
            cached_topics = await self.scoped_cache.get(source_name, params)
            if cached_topics is not None:
                logger.info(f"Got {len(cached_topics)} topics from cache: {source_name}")
                stats.scoped_topics += len(cached_topics)
                return cached_topics

        # Cache miss or unavailable, collect directly
        logger.info(f"Collecting from scoped source: {source_name}")
        topics = await self._collect_directly(source_name, overrides)

        # Store in cache for future use
        if self.scoped_cache and params and topics:
            await self.scoped_cache.set(source_name, params, topics)

        stats.scoped_topics += len(topics)
        logger.info(f"{source_name}: {len(topics)} topics")
        return topics

    async def _collect_directly(
        self,
        source_name: str,
        overrides: dict[str, Any],
    ) -> list[RawTopic]:
        """Collect directly from a source using the factory.

        Args:
            source_name: Name of the source
            overrides: Source-specific overrides

        Returns:
            List of raw topics
        """
        source = create_source(source_name, self.http_client, overrides)
        if source is None:
            logger.warning(f"Unknown or unconfigured source: {source_name}")
            return []

        return await source.collect()

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

        for raw in raw_topics:
            try:
                # Use source_id from raw topic if available, otherwise generate unique ID per topic
                source_id = getattr(raw, "source_id", None)
                if source_id is None:
                    source_id = uuid.uuid4()
                elif isinstance(source_id, str):
                    source_id = uuid.UUID(source_id)

                norm = await self.normalizer.normalize(
                    raw, source_id=source_id, target_language=target_language
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
        config: CollectionConfig,
    ) -> list[tuple[RawTopic, NormalizedTopic, ScoredTopic]]:
        """Score topics.

        Args:
            topics: List of (raw, normalized) tuples
            stats: Stats to update
            config: Collection config with source_overrides

        Returns:
            List of (raw, normalized, scored) tuples
        """
        scored = []
        for raw, norm in topics:
            try:
                # Get source weight from overrides (default 5.0 on 1-10 scale)
                source_name = norm.metadata.get("source_name", "")
                source_config = config.source_overrides.get(source_name, {})
                # weight is typically 1.0-5.0, scale to 1-10 for credibility
                weight = source_config.get("weight", 2.5)
                source_credibility = min(10.0, weight * 2.0)  # 2.0 -> 4.0, 3.0 -> 6.0

                sc = self.scorer.score(norm, source_credibility=source_credibility)
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
