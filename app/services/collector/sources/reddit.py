"""Reddit source collector.

Collects posts from Reddit using the public JSON API.
No authentication required for public subreddits.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import HttpUrl

from app.config.sources import RedditConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

logger = get_logger(__name__)

# Reddit API settings
REDDIT_BASE = "https://www.reddit.com"
USER_AGENT = "BSForge/1.0 (Topic Collection Bot)"


class RedditSource(BaseSource[RedditConfig]):
    """Reddit source collector.

    Fetches posts from specified subreddits using the public JSON API.

    Config options:
        subreddits: List of subreddit names to fetch from
        limit: Posts per subreddit (default: 25)
        min_score: Minimum upvotes (default: 100)
        sort: Sort method - hot, new, top, rising (default: hot)
        time: Time filter for top sort - hour, day, week, month, year, all

    Params override (from channel config):
        subreddits: Override subreddit list
        limit: Override limit per subreddit
        min_score: Override minimum score
    """

    def __init__(
        self,
        config: RedditConfig,
        source_id: uuid.UUID,
    ):
        """Initialize Reddit source collector.

        Args:
            config: Typed configuration object
            source_id: UUID of the source
        """
        super().__init__(config, source_id)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect posts from Reddit subreddits.

        Args:
            params: Optional parameters to override defaults

        Returns:
            List of RawTopic from Reddit
        """
        params = params or {}
        subreddits = params.get("subreddits", self._config.subreddits)
        limit = params.get("limit", self._config.limit)
        min_score = params.get("min_score", self._config.min_score)
        sort = params.get("sort", self._config.sort)
        time_filter = params.get("time", self._config.time)

        if not subreddits:
            logger.warning("No subreddits configured for Reddit source")
            return []

        logger.info(
            "Collecting from Reddit",
            subreddits=subreddits,
            limit=limit,
            min_score=min_score,
            sort=sort,
        )

        topics: list[RawTopic] = []

        async with httpx.AsyncClient(
            timeout=self._config.request_timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for subreddit in subreddits:
                try:
                    posts = await self._fetch_subreddit(client, subreddit, limit, sort, time_filter)
                    for post in posts:
                        if post.get("data", {}).get("score", 0) >= min_score:
                            topic = self._to_raw_topic(post["data"], subreddit)
                            if topic:
                                topics.append(topic)

                except Exception as e:
                    logger.error(
                        "Failed to fetch subreddit",
                        subreddit=subreddit,
                        error=str(e),
                    )
                    continue

        logger.info("Reddit collection complete", collected=len(topics))
        return topics

    async def _fetch_subreddit(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
        limit: int,
        sort: str,
        time_filter: str,
    ) -> list[dict[str, Any]]:
        """Fetch posts from a single subreddit.

        Args:
            client: HTTP client
            subreddit: Subreddit name
            limit: Max posts to fetch
            sort: Sort method
            time_filter: Time filter for top sort

        Returns:
            List of post data
        """
        url = f"{REDDIT_BASE}/r/{subreddit}/{sort}.json"
        params: dict[str, str | int] = {"limit": limit, "raw_json": 1}

        if sort == "top":
            params["t"] = time_filter

        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        children: list[dict[str, Any]] = data.get("data", {}).get("children", [])
        return children

    def _to_raw_topic(self, post: dict[str, Any], subreddit: str) -> RawTopic | None:
        """Convert Reddit post to RawTopic.

        Args:
            post: Reddit post data
            subreddit: Source subreddit name

        Returns:
            RawTopic or None if conversion failed
        """
        try:
            # Skip stickied posts (announcements, rules, etc.)
            if post.get("stickied"):
                return None

            # Skip non-text posts without titles
            if not post.get("title"):
                return None

            # Get URL - prefer external link, fall back to Reddit post
            url = post.get("url")
            if not url or url.startswith("/r/"):
                url = f"{REDDIT_BASE}{post.get('permalink', '')}"

            # Convert Unix timestamp
            published_at = None
            if post.get("created_utc"):
                published_at = datetime.fromtimestamp(post["created_utc"], tz=UTC)

            # Get content - selftext for text posts
            content = post.get("selftext")
            if content == "[removed]" or content == "[deleted]":
                content = None

            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(url),
                title=post["title"],
                content=content,
                published_at=published_at,
                metrics={
                    "score": post.get("score", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "comments": post.get("num_comments", 0),
                    "awards": post.get("total_awards_received", 0),
                },
                metadata={
                    "reddit_id": post.get("id"),
                    "subreddit": subreddit,
                    "author": post.get("author"),
                    "flair": post.get("link_flair_text"),
                    "is_self": post.get("is_self", False),
                    "permalink": f"{REDDIT_BASE}{post.get('permalink', '')}",
                    "domain": post.get("domain"),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to convert Reddit post",
                post_id=post.get("id"),
                error=str(e),
            )
            return None

    async def health_check(self) -> bool:
        """Check if Reddit API is accessible.

        Returns:
            True if API responds successfully
        """
        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                # Check r/all as a basic health check
                response = await client.get(f"{REDDIT_BASE}/r/all/hot.json?limit=1")
                return response.status_code == 200
        except Exception as e:
            logger.warning("Reddit health check failed", error=str(e))
            return False


__all__ = ["RedditSource"]
