"""Source factory for dynamic source instantiation.

This module provides a factory pattern for creating topic sources
based on configuration, enabling config-driven source selection.
"""

import uuid
from typing import Any, Final

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

# Default values for source configuration
DEFAULT_LIMIT: Final[int] = 10
DEFAULT_RSS_LIMIT: Final[int] = 20
DEFAULT_MIN_SCORE_HACKERNEWS: Final[int] = 50
DEFAULT_MIN_SCORE_REDDIT: Final[int] = 30
DEFAULT_MIN_SCORE_KOREAN: Final[int] = 0


def create_source(
    source_name: str,
    overrides: dict[str, Any] | None = None,
    source_id: uuid.UUID | None = None,
) -> "BaseSource[Any] | None":
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
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_HACKERNEWS)
        limit = overrides.get("limit", DEFAULT_LIMIT)
        hn_config = HackerNewsConfig(limit=limit, min_score=min_score)
        return HackerNewsSource(config=hn_config, source_id=source_id)

    elif source_name == "reddit":
        subreddits = overrides.get("params", {}).get("subreddits")
        if not subreddits:
            raise ValueError("reddit requires params.subreddits in overrides")
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_REDDIT)
        limit = overrides.get("limit", DEFAULT_LIMIT)
        reddit_config = RedditConfig(subreddits=subreddits, limit=limit, min_score=min_score)
        return RedditSource(config=reddit_config, source_id=source_id)

    elif source_name == "youtube_trending":
        params = overrides.get("params", {})
        # Support both "region" (single) and "regions" (list)
        regions = params.get("regions") or [params.get("region", "KR")]
        category_id = int(params.get("category", 0))
        limit = overrides.get("limit", DEFAULT_LIMIT)
        yt_config = YouTubeTrendingConfig(regions=regions, category_id=category_id, limit=limit)
        return YouTubeTrendingSource(config=yt_config, source_id=source_id)

    elif source_name == "google_trends":
        params = overrides.get("params", {})
        # Support both "region" (single) and "regions" (list)
        regions = params.get("regions") or [params.get("region", "KR")]
        limit = overrides.get("limit", DEFAULT_LIMIT)
        gt_config = GoogleTrendsConfig(regions=regions, limit=limit)
        return GoogleTrendsSource(config=gt_config, source_id=source_id)

    elif source_name == "dcinside":
        params = overrides.get("params", {})
        galleries = params.get("galleries", ["hit"])
        gallery_type = params.get("gallery_type", "major")
        limit = overrides.get("limit", DEFAULT_LIMIT)
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_KOREAN)
        dc_config = DCInsideConfig(
            galleries=galleries, gallery_type=gallery_type, limit=limit, min_score=min_score
        )
        return DCInsideSource(config=dc_config, source_id=source_id)

    elif source_name == "clien":
        params = overrides.get("params", {})
        boards = params.get("boards", ["park"])
        limit = overrides.get("limit", DEFAULT_LIMIT)
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_KOREAN)
        clien_config = ClienConfig(boards=boards, limit=limit, min_score=min_score)
        return ClienSource(config=clien_config, source_id=source_id)

    elif source_name == "ruliweb":
        params = overrides.get("params", {})
        boards = params.get("boards", ["best/humor"])
        limit = overrides.get("limit", DEFAULT_LIMIT)
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_KOREAN)
        ruliweb_config = RuliwebConfig(boards=boards, limit=limit, min_score=min_score)
        return RuliwebSource(config=ruliweb_config, source_id=source_id)

    elif source_name == "fmkorea":
        params = overrides.get("params", {})
        boards = params.get("boards", ["best"])
        limit = overrides.get("limit", DEFAULT_LIMIT)
        min_score = overrides.get("filters", {}).get("min_score", DEFAULT_MIN_SCORE_KOREAN)
        fmkorea_config = FmkoreaConfig(boards=boards, limit=limit, min_score=min_score)
        return FmkoreaSource(config=fmkorea_config, source_id=source_id)

    elif source_name == "rss" or source_name.endswith("_rss"):
        # Support both "rss" and custom names like "sbs_ent_rss"
        params = overrides.get("params", {})
        feed_url = params.get("feed_url", "")
        if not feed_url:
            logger.warning(f"RSS source '{source_name}' requires feed_url in config")
            return None
        name = params.get("name", source_name)
        limit = overrides.get("limit", DEFAULT_RSS_LIMIT)
        rss_config = RSSConfig(feed_url=feed_url, name=name, limit=limit)
        return RSSSource(config=rss_config, source_id=source_id)

    else:
        logger.warning(f"Unknown source type: {source_name}")
        return None


async def collect_from_sources(
    enabled_sources: list[str],
    source_overrides: dict[str, Any] | None = None,
) -> list[Any]:
    """Collect topics from multiple sources.

    Args:
        enabled_sources: List of source names to collect from
        source_overrides: Per-source configuration overrides

    Returns:
        List of RawTopic objects from all sources
    """
    source_overrides = source_overrides or {}
    all_topics: list[Any] = []

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
