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
- Clien: 클리앙 community scraper
- DCInside: 디시인사이드 gallery scraper

Note: Uses lazy imports to avoid heavy dependencies (pandas) loading at module import.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.collector.sources.clien import ClienSource
    from app.services.collector.sources.dcinside import DCInsideSource
    from app.services.collector.sources.google_trends import GoogleTrendsSource
    from app.services.collector.sources.hackernews import HackerNewsSource
    from app.services.collector.sources.reddit import RedditSource
    from app.services.collector.sources.rss import RSSSource
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
    "ClienSource",
    "DCInsideSource",
]


def __getattr__(name: str):
    """Lazy import for source collectors to avoid loading heavy dependencies."""
    if name == "HackerNewsSource":
        from app.services.collector.sources.hackernews import HackerNewsSource

        return HackerNewsSource
    if name == "RedditSource":
        from app.services.collector.sources.reddit import RedditSource

        return RedditSource
    if name == "YouTubeTrendingSource":
        from app.services.collector.sources.youtube_trending import YouTubeTrendingSource

        return YouTubeTrendingSource
    if name == "RSSSource":
        from app.services.collector.sources.rss import RSSSource

        return RSSSource
    if name == "GoogleTrendsSource":
        from app.services.collector.sources.google_trends import GoogleTrendsSource

        return GoogleTrendsSource
    if name == "WebScraperSource":
        from app.services.collector.sources.web_scraper import WebScraperSource

        return WebScraperSource
    if name == "ClienSource":
        from app.services.collector.sources.clien import ClienSource

        return ClienSource
    if name == "DCInsideSource":
        from app.services.collector.sources.dcinside import DCInsideSource

        return DCInsideSource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
