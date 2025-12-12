"""Topic collection Celery tasks.

This module defines Celery tasks for scheduled topic collection
from various sources (Reddit, HN, RSS, etc.).

Tasks:
- collect_topics: Collect topics from all sources for a channel
- collect_from_source: Collect from a single source
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.services.collector.base import CollectionResult, RawTopic

logger = get_task_logger(__name__)


class CollectionTaskResult(BaseModel):
    """Result of a collection task.

    Attributes:
        channel_id: Channel UUID
        source_results: Results from each source
        total_collected: Total topics collected
        total_processed: Total topics after processing
        started_at: Task start time
        completed_at: Task completion time
        errors: List of error messages
    """

    channel_id: str
    source_results: list[dict[str, Any]]
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
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _get_config_class(source_type: str):
    """Get config class by source type.

    Args:
        source_type: Source type

    Returns:
        Config class
    """
    from app.config.sources import (
        ClienConfig,
        DCInsideConfig,
        GoogleTrendsConfig,
        HackerNewsConfig,
        RedditConfig,
        RSSConfig,
        YouTubeTrendingConfig,
    )

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


async def _collect_from_source_async(
    source_type: str,
    source_id: str,
    source_config: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> CollectionResult:
    """Async implementation of source collection.

    Args:
        source_type: Type of source
        source_id: Source UUID
        source_config: Source configuration dict
        params: Optional collection parameters

    Returns:
        CollectionResult with statistics
    """
    from time import time

    start_time = time()
    errors: list[str] = []
    collected_count = 0

    try:
        # Get source and config classes
        source_class = _get_source_class(source_type)
        config_class = _get_config_class(source_type)

        if not config_class:
            raise ValueError(f"No config class for source type: {source_type}")

        # Create typed config
        config = config_class(**source_config)

        # Create source instance
        source = source_class(config=config, source_id=uuid.UUID(source_id))

        # Collect topics
        raw_topics = await source.collect(params or {})
        collected_count = len(raw_topics)

        logger.info(
            f"Collected {collected_count} topics from {source_type}",
            extra={"source_id": source_id, "source_type": source_type},
        )

    except Exception as e:
        error_msg = f"Collection failed for {source_type}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)

    duration = time() - start_time

    return CollectionResult(
        source_id=uuid.UUID(source_id),
        source_name=source_type,
        collected_count=collected_count,
        errors=errors,
        duration_seconds=duration,
    )


async def _collect_topics_async(
    channel_id: str,
    sources: list[dict[str, Any]],
    target_language: str = "ko",
) -> CollectionTaskResult:
    """Async implementation of topic collection.

    Collects topics from all configured sources for a channel,
    then normalizes, deduplicates, and scores them.

    Args:
        channel_id: Channel UUID
        sources: List of source configurations
        target_language: Target language for translation

    Returns:
        CollectionTaskResult with statistics
    """
    from app.config import DedupConfig, ScoringConfig
    from app.services.collector.deduplicator import TopicDeduplicator
    from app.services.collector.normalizer import TopicNormalizer
    from app.services.collector.scorer import TopicScorer

    started_at = datetime.now(UTC)
    source_results: list[dict[str, Any]] = []
    all_raw_topics: list[tuple[RawTopic, str, str]] = []  # (topic, source_id, source_type)
    errors: list[str] = []

    # Phase 1: Collect from all sources
    for source_def in sources:
        source_type = source_def.get("type", "")
        source_id = source_def.get("id", str(uuid.uuid4()))
        source_config = source_def.get("config", {})
        params = source_def.get("params")

        try:
            result = await _collect_from_source_async(
                source_type=source_type,
                source_id=source_id,
                source_config=source_config,
                params=params,
            )

            source_results.append(result.model_dump())

            if result.errors:
                errors.extend(result.errors)

            # If collection succeeded, re-collect to get actual topics
            # (This is a simplified version; in production, we'd store topics in result)
            if result.collected_count > 0:
                source_class = _get_source_class(source_type)
                config_class = _get_config_class(source_type)
                config = config_class(**source_config)
                source = source_class(config=config, source_id=uuid.UUID(source_id))
                raw_topics = await source.collect(params or {})
                for topic in raw_topics:
                    all_raw_topics.append((topic, source_id, source_type))

        except Exception as e:
            error_msg = f"Source collection error ({source_type}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    total_collected = len(all_raw_topics)
    logger.info(f"Total collected from all sources: {total_collected}")

    # Phase 2: Normalize, deduplicate, and score
    total_processed = 0

    if all_raw_topics:
        try:
            # Initialize services
            redis = AsyncRedis.from_url(str(settings.redis_url))
            normalizer = TopicNormalizer()
            deduplicator = TopicDeduplicator(redis=redis, config=DedupConfig())
            scorer = TopicScorer(config=ScoringConfig())

            for raw_topic, source_id, _source_type in all_raw_topics:
                try:
                    # Normalize
                    normalized = await normalizer.normalize(
                        raw=raw_topic,
                        source_id=uuid.UUID(source_id),
                        target_language=target_language,
                    )

                    # Check for duplicates
                    dedup_result = await deduplicator.is_duplicate(normalized, channel_id)
                    if dedup_result.is_duplicate:
                        logger.debug(f"Duplicate detected: {normalized.title_normalized[:50]}")
                        continue

                    # Score
                    scored = scorer.score(normalized)

                    # Mark as seen
                    await deduplicator.mark_as_seen(normalized, channel_id)

                    total_processed += 1
                    logger.debug(
                        f"Processed topic: {scored.title_normalized[:50]}, score: {scored.score_total}"
                    )

                except Exception as e:
                    error_msg = f"Processing error for topic: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            await redis.aclose()

        except Exception as e:
            error_msg = f"Processing pipeline error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    completed_at = datetime.now(UTC)

    return CollectionTaskResult(
        channel_id=channel_id,
        source_results=source_results,
        total_collected=total_collected,
        total_processed=total_processed,
        started_at=started_at,
        completed_at=completed_at,
        errors=errors,
    )


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
    """Collect topics from a single source.

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

    try:
        result = asyncio.run(
            _collect_from_source_async(
                source_type=source_type,
                source_id=source_id,
                source_config=source_config,
                params=params,
            )
        )
        return result.model_dump()

    except Exception as exc:
        logger.error(f"Collection task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.collect.collect_topics",
    max_retries=3,
    default_retry_delay=300,
)
def collect_topics(
    self,
    channel_id: str,
    sources: list[dict[str, Any]],
    target_language: str = "ko",
) -> dict[str, Any]:
    """Collect topics from all sources for a channel.

    This is the main collection task that:
    1. Collects raw topics from all configured sources
    2. Normalizes topics (translate, classify, clean)
    3. Deduplicates using content hash
    4. Scores topics based on various factors
    5. Queues high-scoring topics for review/generation

    Args:
        self: Celery task instance
        channel_id: Channel UUID
        sources: List of source configurations with format:
            [{"type": "hackernews", "id": "uuid", "config": {...}, "params": {...}}, ...]
        target_language: Target language for translation (default: "ko")

    Returns:
        CollectionTaskResult as dict
    """
    logger.info(f"Starting topic collection for channel: {channel_id}")

    try:
        result = asyncio.run(
            _collect_topics_async(
                channel_id=channel_id,
                sources=sources,
                target_language=target_language,
            )
        )

        logger.info(
            f"Collection complete for channel {channel_id}: "
            f"collected={result.total_collected}, processed={result.total_processed}"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Collection task failed for channel {channel_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


__all__ = [
    "collect_topics",
    "collect_from_source",
    "CollectionTaskResult",
]
