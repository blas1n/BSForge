"""Source factory for dynamic source instantiation.

This module provides a factory pattern for creating topic sources
based on configuration, enabling config-driven source selection.
"""

import uuid
from typing import Any, Final

from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.services.collector.base import BaseSource
from app.services.collector.sources.clien import ClienSource
from app.services.collector.sources.dcinside import DCInsideSource
from app.services.collector.sources.fmkorea import FmkoreaSource
from app.services.collector.sources.google_trends import GoogleTrendsSource
from app.services.collector.sources.hackernews import HackerNewsSource
from app.services.collector.sources.reddit import RedditSource
from app.services.collector.sources.rss import RSSSource
from app.services.collector.sources.ruliweb import RuliwebSource
from app.services.collector.sources.youtube_trending import YouTubeTrendingSource

logger = get_logger(__name__)

# Default values for source configuration
DEFAULT_LIMIT: Final[int] = 10
DEFAULT_RSS_LIMIT: Final[int] = 20

# Source name to class mapping
SOURCE_CLASSES: dict[str, type[BaseSource[Any]]] = {
    "hackernews": HackerNewsSource,
    "reddit": RedditSource,
    "youtube_trending": YouTubeTrendingSource,
    "google_trends": GoogleTrendsSource,
    "dcinside": DCInsideSource,
    "clien": ClienSource,
    "ruliweb": RuliwebSource,
    "fmkorea": FmkoreaSource,
    "rss": RSSSource,
}


def get_source_class(source_name: str) -> type[BaseSource[Any]] | None:
    """Get the source class for a given source name.

    Args:
        source_name: Name of the source (e.g., "hackernews", "reddit")

    Returns:
        Source class or None if source type is unknown
    """
    # Handle custom RSS names like "sbs_ent_rss"
    if source_name.endswith("_rss"):
        return RSSSource
    return SOURCE_CLASSES.get(source_name)


def is_global_source(source_name: str) -> bool:
    """Check if a source is collected globally (shared across all channels).

    Global sources are collected once and shared. Scoped sources require
    channel-specific parameters and are collected per channel.

    Args:
        source_name: Name of the source (e.g., "hackernews", "reddit")

    Returns:
        True if source is global, False if scoped or unknown
    """
    source_class = get_source_class(source_name)
    if source_class is None:
        return False
    return getattr(source_class, "is_global", False)


def create_source(
    source_name: str,
    overrides: dict[str, Any] | None = None,
    source_id: uuid.UUID | None = None,
    http_client: HTTPClient | None = None,
) -> BaseSource[Any]:
    """Create a topic source instance from name and config overrides.

    Each Source class defines its own build_config() classmethod that knows
    how to construct the appropriate config from overrides.

    Args:
        source_name: Name of the source (e.g., "hackernews", "reddit")
        overrides: Configuration overrides from channel config
        source_id: Optional source ID (generates new UUID if not provided)
        http_client: Shared HTTP client for connection reuse

    Returns:
        TopicSource instance

    Raises:
        ValueError: If source type is unknown or required parameters are missing
    """
    source_class = get_source_class(source_name)
    if source_class is None:
        raise ValueError(f"Unknown source type: {source_name}")

    overrides = overrides or {}
    source_id = source_id or uuid.uuid4()

    # Each Source class implements build_config classmethod
    config = source_class.build_config(overrides)

    if config is None:
        raise ValueError(f"Failed to build config for {source_name}")

    return source_class(config=config, source_id=source_id, http_client=http_client)


def get_all_source_names() -> list[str]:
    """Get all registered source names.

    Returns:
        List of source names
    """
    return list(SOURCE_CLASSES.keys())


def get_global_source_names() -> list[str]:
    """Get names of all global sources.

    Returns:
        List of global source names
    """
    return [name for name in SOURCE_CLASSES if is_global_source(name)]


def get_scoped_source_names() -> list[str]:
    """Get names of all scoped sources.

    Returns:
        List of scoped source names
    """
    return [name for name in SOURCE_CLASSES if not is_global_source(name)]


async def collect_from_sources(
    enabled_sources: list[str],
    source_overrides: dict[str, Any] | None = None,
    http_client: HTTPClient | None = None,
) -> list[Any]:
    """Collect topics from multiple sources.

    Args:
        enabled_sources: List of source names to collect from
        source_overrides: Per-source configuration overrides
        http_client: Shared HTTP client for connection reuse

    Returns:
        List of RawTopic objects from all sources
    """
    source_overrides = source_overrides or {}
    all_topics: list[Any] = []

    for source_name in enabled_sources:
        overrides = source_overrides.get(source_name, {})
        try:
            source = create_source(source_name, overrides, http_client=http_client)
            topics = await source.collect()
            all_topics.extend(topics)
            logger.info(f"Collected {len(topics)} topics from {source_name}")
        except Exception as e:
            logger.error(f"Failed to collect from {source_name}: {e}")

    return all_topics


__all__ = [
    "create_source",
    "collect_from_sources",
    "get_source_class",
    "is_global_source",
    "get_all_source_names",
    "get_global_source_names",
    "get_scoped_source_names",
    "SOURCE_CLASSES",
]
