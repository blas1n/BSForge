"""Source collector configuration models.

Defines default settings and configuration for each source type.
"""

from pydantic import BaseModel, Field


class HackerNewsConfig(BaseModel):
    """HackerNews source configuration.

    Attributes:
        limit: Maximum number of stories to fetch
        min_score: Minimum score threshold for filtering
        request_timeout: HTTP request timeout in seconds
    """

    limit: int = Field(default=30, ge=1, le=100)
    min_score: int = Field(default=50, ge=0)
    request_timeout: float = Field(default=10.0, ge=1.0, le=60.0)


class RedditConfig(BaseModel):
    """Reddit source configuration.

    Attributes:
        subreddits: List of subreddits to fetch from
        limit: Maximum posts per subreddit
        min_score: Minimum score threshold
        sort: Sort method (hot, new, top, rising)
        time: Time filter for top posts (hour, day, week, month, year, all)
        request_timeout: HTTP request timeout in seconds
    """

    subreddits: list[str] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=100)
    min_score: int = Field(default=100, ge=0)
    sort: str = Field(default="hot", pattern="^(hot|new|top|rising)$")
    time: str = Field(default="day", pattern="^(hour|day|week|month|year|all)$")
    request_timeout: float = Field(default=10.0, ge=1.0, le=60.0)


class RSSConfig(BaseModel):
    """RSS/Atom feed source configuration.

    Attributes:
        feed_url: URL of the RSS/Atom feed
        name: Display name for the source
        limit: Maximum entries to fetch
        request_timeout: HTTP request timeout in seconds
    """

    feed_url: str | None = None
    name: str = Field(default="RSS Feed")
    limit: int = Field(default=20, ge=1, le=100)
    request_timeout: float = Field(default=15.0, ge=1.0, le=60.0)


class GoogleTrendsConfig(BaseModel):
    """Google Trends source configuration.

    Attributes:
        regions: List of region codes to fetch trends from (e.g., 'KR', 'US')
        limit: Maximum trends to fetch per region
        timeframe: Timeframe for trends (e.g., 'now 1-d', 'now 7-d')
        category: Google Trends category ID (0 = all categories)
    """

    regions: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)
    timeframe: str = Field(default="now 1-d")
    category: int = Field(default=0, ge=0)


class YouTubeTrendingConfig(BaseModel):
    """YouTube Trending source configuration.

    Attributes:
        regions: List of region codes (ISO 3166-1 alpha-2)
        limit: Maximum videos per region
        category_id: YouTube video category ID (0 = all)
        request_timeout: API request timeout in seconds
        api_key: YouTube Data API v3 key (optional, can use settings)
    """

    regions: list[str] = Field(default_factory=lambda: ["KR", "US"])
    limit: int = Field(default=20, ge=1, le=50)
    category_id: int = Field(default=0, ge=0)
    request_timeout: float = Field(default=15.0, ge=1.0, le=60.0)
    api_key: str | None = Field(default=None)


class WebScraperConfig(BaseModel):
    """Generic web scraper configuration.

    Attributes:
        base_url: Base URL for the website
        name: Display name for the source
        limit: Maximum items to scrape
        min_score: Minimum score/views threshold
        request_timeout: HTTP request timeout in seconds
        user_agent: User-Agent header for requests
        rate_limit_delay: Delay between requests in seconds
    """

    base_url: str | None = None
    name: str = Field(default="Web Scraper")
    limit: int = Field(default=20, ge=1, le=100)
    min_score: int = Field(default=0, ge=0)
    request_timeout: float = Field(default=15.0, ge=1.0, le=60.0)
    user_agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    rate_limit_delay: float = Field(default=1.0, ge=0.0, le=10.0)


class DCInsideConfig(WebScraperConfig):
    """DC Inside gallery source configuration.

    Attributes:
        galleries: List of gallery IDs to fetch from
        gallery_type: Type of gallery ('major', 'minor', 'mini')
    """

    base_url: str = Field(default="https://gall.dcinside.com")
    name: str = Field(default="디시인사이드")
    galleries: list[str] = Field(default_factory=lambda: ["programming"])
    gallery_type: str = Field(default="major", pattern="^(major|minor|mini)$")
    min_score: int = Field(default=10, ge=0)


class ClienConfig(WebScraperConfig):
    """Clien community source configuration.

    Attributes:
        boards: List of board IDs to fetch from
    """

    base_url: str = Field(default="https://www.clien.net")
    name: str = Field(default="클리앙")
    boards: list[str] = Field(default_factory=lambda: ["park"])
    min_score: int = Field(default=10, ge=0)


class RuliwebConfig(WebScraperConfig):
    """Ruliweb community source configuration.

    Attributes:
        boards: List of board paths to fetch from (e.g., 'best/humor', 'community/humor')
    """

    base_url: str = Field(default="https://bbs.ruliweb.com")
    name: str = Field(default="루리웹")
    boards: list[str] = Field(default_factory=lambda: ["best/humor"])
    min_score: int = Field(default=10, ge=0)


class FmkoreaConfig(WebScraperConfig):
    """FM Korea community source configuration.

    Attributes:
        boards: List of board IDs to fetch from
    """

    base_url: str = Field(default="https://www.fmkorea.com")
    name: str = Field(default="FM코리아")
    boards: list[str] = Field(default_factory=lambda: ["best"])
    min_score: int = Field(default=10, ge=0)


__all__ = [
    "HackerNewsConfig",
    "RedditConfig",
    "RSSConfig",
    "GoogleTrendsConfig",
    "YouTubeTrendingConfig",
    "WebScraperConfig",
    "DCInsideConfig",
    "ClienConfig",
    "RuliwebConfig",
    "FmkoreaConfig",
]
