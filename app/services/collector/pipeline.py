"""Topic collection pipeline service.

Simplified pipeline for collecting and processing topics:
1. Collect raw topics from sources (Google Trends, Reddit, RSS)
2. Normalize (translate, classify, extract terms)
3. Filter (include/exclude terms)
4. Deduplicate (DB hash-based)
5. Save to database

Usage:
    pipeline = TopicCollectionPipeline(session, http_client, normalizer)
    result = await pipeline.collect_for_channel(channel, config)
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FilteringConfig
from app.core.config_loader import load_defaults
from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.models.channel import Channel
from app.models.topic import Topic, TopicStatus
from app.services.collector.base import NormalizedTopic, RawTopic
from app.services.collector.filter import TopicFilter
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.sources.factory import create_source

logger = get_logger(__name__)


class CollectionStats(BaseModel):
    """Statistics from topic collection pipeline.

    Attributes:
        total_collected: Total raw topics collected
        normalized_count: Topics after normalization
        filtered_count: Topics after filtering
        deduplicated_count: Topics after deduplication
        saved_count: Topics saved to database
        errors: List of error messages
    """

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
        sources: List of source types to collect from
        target_language: Target language for translation
        source_overrides: Per-source configuration overrides
        include: Terms to include
        exclude: Terms to exclude
        max_topics: Maximum topics to process
        save_to_db: Whether to save topics to database
    """

    sources: list[str]
    target_language: str = "ko"
    source_overrides: dict[str, Any] = field(default_factory=dict)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_topics: int = field(default_factory=lambda: _get_collector_defaults().get("max_topics", 20))
    save_to_db: bool = True
    default_topic_status: TopicStatus = TopicStatus.APPROVED

    @classmethod
    def from_channel_config(cls, channel_config: dict[str, Any]) -> CollectionConfig:
        """Create CollectionConfig from channel YAML config.

        Args:
            channel_config: Channel configuration dictionary

        Returns:
            CollectionConfig instance
        """
        defaults = _get_collector_defaults()
        topic_collection = channel_config.get("topic_collection", {})
        filtering = channel_config.get("filtering", {})

        sources = topic_collection.get("sources", [])
        target_language = topic_collection.get("target_language", "ko")

        return cls(
            sources=sources,
            target_language=target_language,
            source_overrides=topic_collection.get("source_overrides", {}),
            include=filtering.get("include", []),
            exclude=filtering.get("exclude", []),
            max_topics=defaults.get("max_topics", 20),
            save_to_db=True,
        )


class TopicCollectionPipeline:
    """Simplified topic collection pipeline.

    Pipeline: Collect → Normalize → Filter → Dedup (DB) → Save
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: HTTPClient,
        normalizer: TopicNormalizer,
    ) -> None:
        """Initialize pipeline.

        Args:
            session: Database session
            http_client: HTTP client for source requests
            normalizer: Topic normalizer
        """
        self.session = session
        self.http_client = http_client
        self.normalizer = normalizer

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
        logger.info("starting_collection", channel=channel.name)

        # Step 1: Collect raw topics from all sources
        raw_topics = await self._collect_raw_topics(config, stats)

        if not raw_topics:
            logger.warning("no_raw_topics", channel=channel.name)
            return [], stats

        stats.total_collected = len(raw_topics)

        # Step 2: Normalize
        normalized = await self._normalize_topics(raw_topics, config.target_language, stats)
        if not normalized:
            return [], stats
        stats.normalized_count = len(normalized)

        # Step 3: Filter
        filtered = self._filter_topics(normalized, config)
        if not filtered:
            return [], stats
        stats.filtered_count = len(filtered)

        # Step 4: Deduplicate (DB-based)
        deduplicated = await self._deduplicate_topics(filtered, channel.id)
        stats.deduplicated_count = len(deduplicated)

        # Step 5: Save to DB
        topic_status = config.default_topic_status
        if config.save_to_db:
            saved = await self._save_topics(channel, deduplicated, config.max_topics, topic_status)
            stats.saved_count = len(saved)
            return saved, stats

        topics = [
            self._create_topic_model(channel, raw, norm, status=topic_status)
            for raw, norm in deduplicated[: config.max_topics]
        ]
        return topics, stats

    async def _collect_raw_topics(
        self,
        config: CollectionConfig,
        stats: CollectionStats,
    ) -> list[RawTopic]:
        """Collect raw topics from all configured sources."""
        all_topics: list[RawTopic] = []

        for source_name in config.sources:
            overrides = config.source_overrides.get(source_name, {})
            try:
                source = create_source(source_name, self.http_client, overrides)
                topics = await source.collect()
                all_topics.extend(topics)
                logger.info("source_collected", source=source_name, count=len(topics))
            except Exception as e:
                error_msg = f"{source_name} collection failed: {e}"
                logger.error(error_msg, exc_info=True)
                stats.errors.append(error_msg)

        return all_topics

    async def _normalize_topics(
        self,
        raw_topics: list[RawTopic],
        target_language: str,
        stats: CollectionStats,
    ) -> list[tuple[RawTopic, NormalizedTopic]]:
        """Normalize raw topics."""
        normalized: list[tuple[RawTopic, NormalizedTopic]] = []

        for raw in raw_topics:
            try:
                source_id = getattr(raw, "source_id", None)
                if source_id is None:
                    source_id = uuid.uuid4()
                elif isinstance(source_id, str):
                    try:
                        source_id = uuid.UUID(source_id)
                    except ValueError:
                        logger.warning(f"Invalid UUID '{source_id}', generating new one")
                        source_id = uuid.uuid4()

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
        """Filter topics by include/exclude terms."""
        if not config.include and not config.exclude:
            return normalized

        filter_config = FilteringConfig(
            include=config.include,
            exclude=config.exclude,
        )
        topic_filter = TopicFilter(filter_config)

        return [(raw, norm) for raw, norm in normalized if topic_filter.filter(norm).passed]

    @staticmethod
    def _compute_content_hash(norm: NormalizedTopic) -> str:
        """Compute content hash for deduplication.

        Args:
            norm: Normalized topic

        Returns:
            SHA-256 hex digest
        """
        return hashlib.sha256((norm.title_normalized + str(norm.source_url)).encode()).hexdigest()

    async def _deduplicate_topics(
        self,
        topics: list[tuple[RawTopic, NormalizedTopic]],
        channel_id: uuid.UUID,
    ) -> list[tuple[RawTopic, NormalizedTopic]]:
        """Remove duplicate topics using batch DB hash check."""
        if not topics:
            return []

        # Compute hashes once and batch-query existing ones
        hash_map: dict[str, tuple[RawTopic, NormalizedTopic]] = {}
        for raw, norm in topics:
            content_hash = self._compute_content_hash(norm)
            hash_map[content_hash] = (raw, norm)

        result = await self.session.execute(
            select(Topic.content_hash).where(
                Topic.channel_id == channel_id,
                Topic.content_hash.in_(hash_map.keys()),
            )
        )
        existing_hashes = {row[0] for row in result}

        return [pair for h, pair in hash_map.items() if h not in existing_hashes]

    async def _save_topics(
        self,
        channel: Channel,
        topics: list[tuple[RawTopic, NormalizedTopic]],
        max_topics: int,
        status: TopicStatus = TopicStatus.APPROVED,
    ) -> list[Topic]:
        """Save topics to database."""
        saved: list[Topic] = []

        for raw, norm in topics[:max_topics]:
            topic = self._create_topic_model(channel, raw, norm, status=status)
            self.session.add(topic)
            saved.append(topic)

        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error("topic_commit_failed", error=str(e), count=len(saved))
            saved.clear()
            raise

        return saved

    def _create_topic_model(
        self,
        channel: Channel,
        raw: RawTopic,
        norm: NormalizedTopic,
        content_hash: str | None = None,
        status: TopicStatus = TopicStatus.APPROVED,
    ) -> Topic:
        """Create Topic model from processed data."""
        if content_hash is None:
            content_hash = self._compute_content_hash(norm)
        published_at = norm.published_at
        expires_at = (published_at or datetime.now(UTC)) + timedelta(days=7)

        return Topic(
            id=uuid.uuid4(),
            channel_id=channel.id,
            source_id=norm.source_id,
            title_original=raw.title,
            title_translated=norm.title_translated,
            title_normalized=norm.title_normalized,
            summary=norm.summary or (raw.content[:200] if raw.content else ""),
            source_url=str(norm.source_url),
            terms=norm.terms or [],
            entities={},
            language=norm.language or "en",
            score_source=0.0,
            score_freshness=0.0,
            score_trend=0.0,
            score_relevance=0.0,
            score_total=0.0,
            status=status,
            published_at=published_at,
            expires_at=expires_at,
            content_hash=content_hash,
        )


__all__ = [
    "TopicCollectionPipeline",
    "CollectionConfig",
    "CollectionStats",
]
