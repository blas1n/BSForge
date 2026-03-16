"""Source collector configuration models.

Defines default settings and configuration for each source type.
"""

from pydantic import BaseModel, Field


class RedditConfig(BaseModel):
    """Reddit source configuration.

    Attributes:
        subreddits: List of subreddits to fetch from
        limit: Maximum posts per subreddit
        min_score: Minimum score threshold
        sort: Sort method (hot, new, top, rising)
        time: Time filter for top posts
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
        regions: List of region codes to fetch trends from
        limit: Maximum trends to fetch per region
        timeframe: Timeframe for trends
        category: Google Trends category ID (0 = all)
    """

    regions: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)
    timeframe: str = Field(default="now 1-d")
    category: int = Field(default=0, ge=0)


__all__ = [
    "RedditConfig",
    "RSSConfig",
    "GoogleTrendsConfig",
]
