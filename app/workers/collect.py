"""Topic collection Celery tasks.

This module defines Celery tasks for scheduled topic collection
using a hybrid approach:

1. Global sources (HN, Trends, YouTube): Collected once, shared via GlobalTopicPool
2. Scoped sources (Reddit, DCInside, Clien): Collected per channel with caching

Tasks:
- collect_global_sources: Collect all global sources to shared pool
- collect_channel_topics: Hybrid collection for a channel (pool + scoped)
- collect_from_source: Collect from a single source (utility)
"""

import asyncio
import importlib
import uuid
from datetime import UTC, datetime
from time import time
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis

from app.config import DedupConfig, ScoringConfig
from app.config.sources import (
    ClienConfig,
    DCInsideConfig,
    GoogleTrendsConfig,
    HackerNewsConfig,
    RedditConfig,
    RSSConfig,
    YouTubeTrendingConfig,
)

# TODO: This module is legacy and should be migrated to DI container.
from app.core.config import get_config
from app.services.collector.base import CollectionResult, RawTopic
from app.services.collector.deduplicator import TopicDeduplicator
from app.services.collector.global_pool import (
    SOURCE_SCOPES,
    GlobalTopicPool,
    ScopedSourceCache,
    SourceScope,
    is_global_source,
)
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.scorer import TopicScorer

logger = get_task_logger(__name__)


class GlobalCollectionResult(BaseModel):
    """Result of global source collection.

    Attributes:
        source_results: Results per source type
        total_collected: Total topics across all sources
        started_at: Task start time
        completed_at: Task completion time
        errors: List of error messages
    """

    source_results: dict[str, int]  # source_type -> count
    total_collected: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    errors: list[str] = []


class ChannelCollectionResult(BaseModel):
    """Result of channel topic collection.

    Attributes:
        channel_id: Channel UUID
        global_topics: Topics pulled from global pool
        scoped_topics: Topics collected from scoped sources
        total_collected: Total raw topics
        total_processed: Topics after dedup/filtering
        started_at: Task start time
        completed_at: Task completion time
        errors: List of error messages
    """

    channel_id: str
    global_topics: int = 0
    scoped_topics: int = 0
    total_collected: int = 0
    total_processed: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    errors: list[str] = []


def _get_source_class(source_type: str):
    """Get source class by type name.

    Args:
        source_type: Source type (hackernews, reddit, rss, etc.)

    Returns:
        Source class

    Raises:
        ValueError: If source type is unknown
    """
    source_map = {
        "hackernews": ("app.services.collector.sources.hackernews", "HackerNewsSource"),
        "reddit": ("app.services.collector.sources.reddit", "RedditSource"),
        "rss": ("app.services.collector.sources.rss", "RSSSource"),
        "youtube_trending": (
            "app.services.collector.sources.youtube_trending",
            "YouTubeTrendingSource",
        ),
        "google_trends": ("app.services.collector.sources.google_trends", "GoogleTrendsSource"),
        "dcinside": ("app.services.collector.sources.dcinside", "DCInsideSource"),
        "clien": ("app.services.collector.sources.clien", "ClienSource"),
    }

    if source_type not in source_map:
        raise ValueError(f"Unknown source type: {source_type}")

    module_path, class_name = source_map[source_type]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _get_config_class(source_type: str):
    """Get config class by source type.

    Args:
        source_type: Source type

    Returns:
        Config class or None if unknown
    """
    config_map = {
        "hackernews": HackerNewsConfig,
        "reddit": RedditConfig,
        "rss": RSSConfig,
        "youtube_trending": YouTubeTrendingConfig,
        "google_trends": GoogleTrendsConfig,
        "dcinside": DCInsideConfig,
        "clien": ClienConfig,
    }

    return config_map.get(source_type)


async def _collect_source_topics(
    source_type: str,
    source_config: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[RawTopic]:
    """Collect topics from a single source.

    Args:
        source_type: Type of source
        source_config: Source configuration dict (uses defaults if None)
        params: Optional collection parameters

    Returns:
        List of RawTopic
    """
    try:
        source_class = _get_source_class(source_type)
        config_class = _get_config_class(source_type)

        if not config_class:
            raise ValueError(f"No config class for source type: {source_type}")

        config = config_class(**(source_config or {}))
        source = source_class(config=config, source_id=uuid.uuid4())

        topics: list[RawTopic] = await source.collect(params or {})
        return topics

    except Exception as e:
        logger.error(f"Collection failed for {source_type}: {e}", exc_info=True)
        return []


async def _collect_global_sources_async() -> GlobalCollectionResult:
    """Collect all global sources and store in GlobalTopicPool.

    Returns:
        GlobalCollectionResult with statistics
    """
    started_at = datetime.now(UTC)
    source_results: dict[str, int] = {}
    errors: list[str] = []
    total_collected = 0

    redis = AsyncRedis.from_url(str(get_config().redis_url))
    pool = GlobalTopicPool(redis)

    # Get all global source types
    global_sources = [
        source_type for source_type, scope in SOURCE_SCOPES.items() if scope == SourceScope.GLOBAL
    ]

    for source_type in global_sources:
        try:
            logger.info(f"Collecting global source: {source_type}")
            topics = await _collect_source_topics(source_type)

            if topics:
                await pool.add_topics(source_type, topics)
                source_results[source_type] = len(topics)
                total_collected += len(topics)
                logger.info(f"Added {len(topics)} topics to global pool for {source_type}")
            else:
                source_results[source_type] = 0
                logger.warning(f"No topics collected for {source_type}")

        except Exception as e:
            error_msg = f"Global collection error ({source_type}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
            source_results[source_type] = 0

    await redis.aclose()

    return GlobalCollectionResult(
        source_results=source_results,
        total_collected=total_collected,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        errors=errors,
    )


async def _collect_channel_topics_async(
    channel_id: str,
    global_sources: list[str],
    scoped_sources: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    target_language: str = "ko",
) -> ChannelCollectionResult:
    """Hybrid collection for a channel.

    1. Pull topics from GlobalTopicPool for configured global sources
    2. Collect scoped sources directly (with caching)
    3. Apply channel filters
    4. Normalize, deduplicate, score

    Args:
        channel_id: Channel UUID
        global_sources: List of global source types to pull from pool
        scoped_sources: List of scoped source configs
            [{"type": "reddit", "params": {"subreddits": [...]}}]
        filters: Channel-specific filters for global topics
        target_language: Target language for translation

    Returns:
        ChannelCollectionResult with statistics
    """
    started_at = datetime.now(UTC)
    errors: list[str] = []
    all_raw_topics: list[tuple[RawTopic, str]] = []  # (topic, source_type)

    redis = AsyncRedis.from_url(str(get_config().redis_url))
    pool = GlobalTopicPool(redis)
    scoped_cache = ScopedSourceCache(redis)

    global_topic_count = 0
    scoped_topic_count = 0

    # Phase 1: Pull from Global Pool
    for source_type in global_sources:
        if not is_global_source(source_type):
            logger.warning(f"{source_type} is not a global source, skipping pool pull")
            continue

        try:
            topics = await pool.get_topics(source_type)

            if not topics:
                logger.warning(f"No topics in pool for {source_type}, pool may need refresh")
                continue

            # Apply channel filters to global topics
            if filters:
                filtered_topics = []
                for topic in topics:
                    # Simple term filter on raw topics
                    include_terms = filters.get("include", [])
                    exclude_terms = filters.get("exclude", [])

                    title_lower = topic.title.lower()

                    if exclude_terms and any(term.lower() in title_lower for term in exclude_terms):
                        continue

                    if include_terms and not any(
                        term.lower() in title_lower for term in include_terms
                    ):
                        continue

                    filtered_topics.append(topic)

                topics = filtered_topics

            for topic in topics:
                all_raw_topics.append((topic, source_type))

            global_topic_count += len(topics)
            logger.info(f"Pulled {len(topics)} topics from pool for {source_type}")

        except Exception as e:
            error_msg = f"Pool pull error ({source_type}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    # Phase 2: Collect Scoped Sources (with caching)
    for source_def in scoped_sources:
        source_type = source_def.get("type", "")
        params = source_def.get("params", {})
        config = source_def.get("config", {})

        if is_global_source(source_type):
            logger.warning(f"{source_type} is a global source, use global_sources instead")
            continue

        try:
            # Use cache for scoped sources
            # Capture config in default argument to avoid closure issue
            async def collector(
                st: str, p: dict[str, Any], cfg: dict[str, Any] = config
            ) -> list[RawTopic]:
                return await _collect_source_topics(st, cfg, p)

            topics = await scoped_cache.get_or_collect(
                source_type=source_type,
                params=params,
                collector_func=lambda st=source_type, p=params: collector(st, p),
            )

            for topic in topics:
                all_raw_topics.append((topic, source_type))

            scoped_topic_count += len(topics)
            logger.info(f"Collected {len(topics)} topics from {source_type} (params: {params})")

        except Exception as e:
            error_msg = f"Scoped collection error ({source_type}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    total_collected = len(all_raw_topics)
    logger.info(
        f"Channel {channel_id}: collected {total_collected} topics "
        f"(global: {global_topic_count}, scoped: {scoped_topic_count})"
    )

    # Phase 3: Process (normalize, dedupe, score)
    total_processed = 0

    if all_raw_topics:
        try:
            normalizer = TopicNormalizer()
            deduplicator = TopicDeduplicator(redis=redis, config=DedupConfig())
            scorer = TopicScorer(config=ScoringConfig())

            for raw_topic, _source_type in all_raw_topics:
                try:
                    # Normalize
                    normalized = await normalizer.normalize(
                        raw=raw_topic,
                        source_id=uuid.uuid4(),  # Generate new ID for this channel
                        target_language=target_language,
                    )

                    # Check for duplicates
                    dedup_result = await deduplicator.is_duplicate(normalized, channel_id)
                    if dedup_result.is_duplicate:
                        continue

                    # Score (result used for queue in future)
                    scorer.score(normalized)

                    # Mark as seen
                    await deduplicator.mark_as_seen(normalized, channel_id)

                    total_processed += 1

                except Exception as e:
                    error_msg = f"Processing error: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

        except Exception as e:
            error_msg = f"Processing pipeline error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    await redis.aclose()

    return ChannelCollectionResult(
        channel_id=channel_id,
        global_topics=global_topic_count,
        scoped_topics=scoped_topic_count,
        total_collected=total_collected,
        total_processed=total_processed,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        errors=errors,
    )


# =============================================================================
# Celery Tasks
# =============================================================================


@shared_task(
    bind=True,
    name="app.workers.collect.collect_global_sources",
    max_retries=3,
    default_retry_delay=300,
)
def collect_global_sources(self) -> dict[str, Any]:
    """Collect all global sources to shared pool.

    This task should run on a fixed schedule (e.g., every 2 hours)
    BEFORE channel collection tasks to ensure fresh pool data.

    Global sources: hackernews, google_trends, youtube_trending

    Returns:
        GlobalCollectionResult as dict
    """
    logger.info("Starting global source collection")

    try:
        result = asyncio.run(_collect_global_sources_async())

        logger.info(
            f"Global collection complete: {result.total_collected} topics "
            f"from {len(result.source_results)} sources"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Global collection failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.collect.collect_channel_topics",
    max_retries=3,
    default_retry_delay=300,
)
def collect_channel_topics(
    self,
    channel_id: str,
    global_sources: list[str],
    scoped_sources: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    target_language: str = "ko",
) -> dict[str, Any]:
    """Hybrid topic collection for a channel.

    1. Pulls topics from GlobalTopicPool for specified global sources
    2. Collects scoped sources directly (with caching)
    3. Applies channel-specific filters
    4. Normalizes, deduplicates, and scores

    Args:
        self: Celery task instance
        channel_id: Channel UUID
        global_sources: Global source types to pull from pool
            e.g., ["hackernews", "google_trends"]
        scoped_sources: Scoped source definitions
            e.g., [{"type": "reddit", "params": {"subreddits": ["python"]}}]
        filters: Filters for global topics
            e.g., {"include": ["AI"], "exclude": ["광고"]}
        target_language: Target language (default: "ko")

    Returns:
        ChannelCollectionResult as dict
    """
    logger.info(f"Starting hybrid collection for channel: {channel_id}")

    try:
        result = asyncio.run(
            _collect_channel_topics_async(
                channel_id=channel_id,
                global_sources=global_sources,
                scoped_sources=scoped_sources,
                filters=filters,
                target_language=target_language,
            )
        )

        logger.info(
            f"Channel {channel_id} collection complete: "
            f"collected={result.total_collected}, processed={result.total_processed}"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Channel collection failed for {channel_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.collect.collect_from_source",
    max_retries=3,
    default_retry_delay=60,
)
def collect_from_source(
    self,
    source_type: str,
    source_id: str,
    source_config: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect topics from a single source (utility task).

    Args:
        self: Celery task instance
        source_type: Type of source (hackernews, reddit, etc.)
        source_id: Source UUID
        source_config: Source configuration dict
        params: Optional collection parameters

    Returns:
        CollectionResult as dict
    """
    logger.info(f"Starting collection from source: {source_type}")

    start_time = time()
    errors: list[str] = []

    try:
        topics = asyncio.run(
            _collect_source_topics(
                source_type=source_type,
                source_config=source_config,
                params=params,
            )
        )

        duration = time() - start_time

        result = CollectionResult(
            source_id=uuid.UUID(source_id),
            source_name=source_type,
            collected_count=len(topics),
            errors=errors,
            duration_seconds=duration,
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Collection task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


__all__ = [
    "collect_global_sources",
    "collect_channel_topics",
    "collect_from_source",
    "GlobalCollectionResult",
    "ChannelCollectionResult",
]
