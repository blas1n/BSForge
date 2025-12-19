"""Source factory for dynamic source instantiation.

This module provides a factory pattern for creating topic sources
based on configuration, enabling config-driven source selection.
"""

import uuid
from typing import Any

from app.config.sources import (
    ClienConfig,
    DCInsideConfig,
    FmkoreaConfig,
    GoogleTrendsConfig,
    HackerNewsConfig,
    RedditConfig,
    RSSConfig,
    RuliwebConfig,
    YouTubeTrendingConfig,
)
from app.core.logging import get_logger
from app.services.collector.base import BaseSource

logger = get_logger(__name__)


def create_source(
    source_name: str,
    overrides: dict[str, Any] | None = None,
    source_id: uuid.UUID | None = None,
) -> BaseSource | None:
    """Create a topic source instance from name and config overrides.

    Args:
        source_name: Name of the source (e.g., "hackernews", "reddit")
        overrides: Configuration overrides from channel config
        source_id: Optional source ID (generates new UUID if not provided)

    Returns:
        TopicSource instance or None if source type is unknown
    """
    # Lazy imports to avoid circular dependencies
    from app.services.collector.sources.clien import ClienSource
    from app.services.collector.sources.dcinside import DCInsideSource
    from app.services.collector.sources.fmkorea import FmkoreaSource
    from app.services.collector.sources.google_trends import GoogleTrendsSource
    from app.services.collector.sources.hackernews import HackerNewsSource
    from app.services.collector.sources.reddit import RedditSource
    from app.services.collector.sources.rss import RSSSource
    from app.services.collector.sources.ruliweb import RuliwebSource
    from app.services.collector.sources.youtube_trending import YouTubeTrendingSource

    overrides = overrides or {}
    source_id = source_id or uuid.uuid4()

    if source_name == "hackernews":
        min_score = overrides.get("filters", {}).get("min_score", 50)
        limit = overrides.get("limit", 10)
        config = HackerNewsConfig(limit=limit, min_score=min_score)
        return HackerNewsSource(config=config, source_id=source_id)

    elif source_name == "reddit":
        subreddits = overrides.get("params", {}).get("subreddits", ["news", "worldnews"])
        min_score = overrides.get("filters", {}).get("min_score", 30)
        limit = overrides.get("limit", 10)
        config = RedditConfig(subreddits=subreddits, limit=limit, min_score=min_score)
        return RedditSource(config=config, source_id=source_id)

    elif source_name == "youtube_trending":
        region = overrides.get("params", {}).get("region", "KR")
        category = overrides.get("params", {}).get("category", "0")
        limit = overrides.get("limit", 10)
        config = YouTubeTrendingConfig(region=region, category_id=category, limit=limit)
        return YouTubeTrendingSource(config=config, source_id=source_id)

    elif source_name == "google_trends":
        region = overrides.get("params", {}).get("region", "south_korea")
        limit = overrides.get("limit", 10)
        config = GoogleTrendsConfig(region=region, limit=limit)
        return GoogleTrendsSource(config=config, source_id=source_id)

    elif source_name == "dcinside":
        params = overrides.get("params", {})
        galleries = params.get("galleries", ["hit"])
        gallery_type = params.get("gallery_type", "major")
        limit = overrides.get("limit", 10)
        min_score = overrides.get("filters", {}).get("min_score", 0)
        config = DCInsideConfig(
            galleries=galleries, gallery_type=gallery_type, limit=limit, min_score=min_score
        )
        return DCInsideSource(config=config, source_id=source_id)

    elif source_name == "clien":
        params = overrides.get("params", {})
        boards = params.get("boards", ["park"])
        limit = overrides.get("limit", 10)
        min_score = overrides.get("filters", {}).get("min_score", 0)
        config = ClienConfig(boards=boards, limit=limit, min_score=min_score)
        return ClienSource(config=config, source_id=source_id)

    elif source_name == "ruliweb":
        params = overrides.get("params", {})
        boards = params.get("boards", ["best/humor"])
        limit = overrides.get("limit", 10)
        min_score = overrides.get("filters", {}).get("min_score", 0)
        config = RuliwebConfig(boards=boards, limit=limit, min_score=min_score)
        return RuliwebSource(config=config, source_id=source_id)

    elif source_name == "fmkorea":
        params = overrides.get("params", {})
        boards = params.get("boards", ["best"])
        limit = overrides.get("limit", 10)
        min_score = overrides.get("filters", {}).get("min_score", 0)
        config = FmkoreaConfig(boards=boards, limit=limit, min_score=min_score)
        return FmkoreaSource(config=config, source_id=source_id)

    elif source_name == "rss" or source_name.endswith("_rss"):
        # Support both "rss" and custom names like "sbs_ent_rss"
        params = overrides.get("params", {})
        feed_url = params.get("feed_url", "")
        if not feed_url:
            logger.warning(f"RSS source '{source_name}' requires feed_url in config")
            return None
        name = params.get("name", source_name)
        limit = overrides.get("limit", 20)
        config = RSSConfig(feed_url=feed_url, name=name, limit=limit)
        return RSSSource(config=config, source_id=source_id)

    else:
        logger.warning(f"Unknown source type: {source_name}")
        return None


async def collect_from_sources(
    enabled_sources: list[str],
    source_overrides: dict[str, Any] | None = None,
) -> list:
    """Collect topics from multiple sources.

    Args:
        enabled_sources: List of source names to collect from
        source_overrides: Per-source configuration overrides

    Returns:
        List of RawTopic objects from all sources
    """
    source_overrides = source_overrides or {}
    all_topics = []

    for source_name in enabled_sources:
        overrides = source_overrides.get(source_name, {})
        source = create_source(source_name, overrides)

        if source is None:
            continue

        try:
            topics = await source.collect()
            all_topics.extend(topics)
            logger.info(f"Collected {len(topics)} topics from {source_name}")
        except Exception as e:
            logger.error(f"Failed to collect from {source_name}: {e}")

    return all_topics


__all__ = ["create_source", "collect_from_sources"]
