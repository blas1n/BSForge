"""Source collectors for topic collection.

This package contains implementations of various source collectors:

API Sources:
- HackerNews: Hacker News Firebase API collector
- Reddit: Reddit JSON API collector
- YouTubeTrending: YouTube Data API v3 trending collector

Feed Sources:
- RSS: Generic RSS/Atom feed collector

Trend Sources:
- GoogleTrends: Google Trends collector using pytrends

Scraper Sources:
- WebScraperSource: Base class for HTML scraping
- KoreanWebScraperBase: Base class for Korean community scrapers
- Clien: 클리앙 community scraper
- DCInside: 디시인사이드 gallery scraper
- Ruliweb: 루리웹 community scraper
- Fmkorea: FM코리아 community scraper

Note: Uses lazy imports to avoid heavy dependencies (pandas) loading at module import.
"""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.services.collector.sources.clien import ClienSource
    from app.services.collector.sources.dcinside import DCInsideSource
    from app.services.collector.sources.fmkorea import FmkoreaSource
    from app.services.collector.sources.google_trends import GoogleTrendsSource
    from app.services.collector.sources.hackernews import HackerNewsSource
    from app.services.collector.sources.korean_scraper_base import KoreanWebScraperBase
    from app.services.collector.sources.reddit import RedditSource
    from app.services.collector.sources.rss import RSSSource
    from app.services.collector.sources.ruliweb import RuliwebSource
    from app.services.collector.sources.web_scraper import WebScraperSource
    from app.services.collector.sources.youtube_trending import YouTubeTrendingSource

__all__ = [
    # API sources
    "HackerNewsSource",
    "RedditSource",
    "YouTubeTrendingSource",
    # Feed sources
    "RSSSource",
    # Trend sources
    "GoogleTrendsSource",
    # Scraper sources
    "WebScraperSource",
    "KoreanWebScraperBase",
    "ClienSource",
    "DCInsideSource",
    "RuliwebSource",
    "FmkoreaSource",
]


# Registry for lazy loading source classes
_SOURCE_REGISTRY: dict[str, tuple[str, str]] = {
    # API sources
    "HackerNewsSource": ("hackernews", "HackerNewsSource"),
    "RedditSource": ("reddit", "RedditSource"),
    "YouTubeTrendingSource": ("youtube_trending", "YouTubeTrendingSource"),
    # Feed sources
    "RSSSource": ("rss", "RSSSource"),
    # Trend sources
    "GoogleTrendsSource": ("google_trends", "GoogleTrendsSource"),
    # Scraper base classes
    "WebScraperSource": ("web_scraper", "WebScraperSource"),
    "KoreanWebScraperBase": ("korean_scraper_base", "KoreanWebScraperBase"),
    # Korean scrapers
    "ClienSource": ("clien", "ClienSource"),
    "DCInsideSource": ("dcinside", "DCInsideSource"),
    "RuliwebSource": ("ruliweb", "RuliwebSource"),
    "FmkoreaSource": ("fmkorea", "FmkoreaSource"),
}


def __getattr__(name: str) -> type:
    """Lazy import for source collectors to avoid loading heavy dependencies."""
    if name in _SOURCE_REGISTRY:
        module_name, class_name = _SOURCE_REGISTRY[name]
        module = __import__(
            f"app.services.collector.sources.{module_name}",
            fromlist=[class_name],
        )
        return cast(type, getattr(module, class_name))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
