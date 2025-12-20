"""Hacker News source collector.

Collects top stories from Hacker News using the official Firebase API.
https://github.com/HackerNews/API
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import HttpUrl

from app.config.sources import HackerNewsConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

logger = get_logger(__name__)

# HN API endpoints
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_TOP_STORIES = f"{HN_API_BASE}/topstories.json"
HN_ITEM = f"{HN_API_BASE}/item/{id}.json"


class HackerNewsSource(BaseSource[HackerNewsConfig]):
    """Hacker News source collector.

    Fetches top stories from HN using the official API.

    Config options:
        limit: Maximum number of stories to fetch (default: 30)
        min_score: Minimum score threshold (default: 50)

    Params override (from channel config):
        limit: Override default limit
        min_score: Override minimum score
    """

    def __init__(
        self,
        config: HackerNewsConfig,
        source_id: uuid.UUID,
    ):
        """Initialize HackerNews source collector.

        Args:
            config: Typed configuration object
            source_id: UUID of the source
        """
        super().__init__(config, source_id)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect top stories from Hacker News.

        Args:
            params: Optional parameters to override defaults
                - limit: Max stories to fetch
                - min_score: Minimum score filter

        Returns:
            List of RawTopic from HN
        """
        params = params or {}
        limit = params.get("limit", self._config.limit)
        min_score = params.get("min_score", self._config.min_score)

        logger.info(
            "Collecting from Hacker News",
            limit=limit,
            min_score=min_score,
        )

        try:
            async with httpx.AsyncClient(timeout=self._config.request_timeout) as client:
                # Get top story IDs
                response = await client.get(HN_TOP_STORIES)
                response.raise_for_status()
                story_ids = response.json()[: limit * 2]  # Fetch extra to account for filtering

                # Fetch individual stories
                topics: list[RawTopic] = []
                for story_id in story_ids:
                    if len(topics) >= limit:
                        break

                    story = await self._fetch_story(client, story_id)
                    if story and story.get("score", 0) >= min_score:
                        topic = self._to_raw_topic(story)
                        if topic:
                            topics.append(topic)

                logger.info(
                    "Hacker News collection complete",
                    collected=len(topics),
                    fetched=len(story_ids),
                )
                return topics

        except httpx.HTTPError as e:
            logger.error("HN API request failed", error=str(e))
            raise
        except Exception as e:
            logger.error("HN collection failed", error=str(e), exc_info=True)
            raise

    async def _fetch_story(self, client: httpx.AsyncClient, story_id: int) -> dict[str, Any] | None:
        """Fetch a single story by ID.

        Args:
            client: HTTP client
            story_id: HN story ID

        Returns:
            Story data or None if fetch failed
        """
        try:
            url = HN_ITEM.format(id=story_id)
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # Skip non-story items (comments, jobs, etc.)
            if data and data.get("type") == "story":
                story_data: dict[str, Any] = data
                return story_data
            return None

        except httpx.HTTPError as e:
            logger.warning("Failed to fetch HN story", story_id=story_id, error=str(e))
            return None

    def _to_raw_topic(self, story: dict[str, Any]) -> RawTopic | None:
        """Convert HN story to RawTopic.

        Args:
            story: HN story data

        Returns:
            RawTopic or None if conversion failed
        """
        try:
            # HN stories may not have URL (Ask HN, Show HN text posts)
            url = story.get("url")
            if not url:
                # Use HN discussion URL for text posts
                url = f"https://news.ycombinator.com/item?id={story['id']}"

            # Convert Unix timestamp to datetime
            published_at = None
            if story.get("time"):
                published_at = datetime.fromtimestamp(story["time"], tz=UTC)

            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(url),
                title=story["title"],
                content=story.get("text"),  # Text content for Ask HN, etc.
                published_at=published_at,
                metrics={
                    "score": story.get("score", 0),
                    "comments": story.get("descendants", 0),
                },
                metadata={
                    "source_name": "HackerNews",
                    "hn_id": story["id"],
                    "by": story.get("by"),
                    "type": story.get("type"),
                    "hn_url": f"https://news.ycombinator.com/item?id={story['id']}",
                },
            )
        except Exception as e:
            logger.warning("Failed to convert HN story", story_id=story.get("id"), error=str(e))
            return None

    async def health_check(self) -> bool:
        """Check if HN API is accessible.

        Returns:
            True if API responds successfully
        """
        try:
            async with httpx.AsyncClient(timeout=self._config.request_timeout) as client:
                response = await client.get(HN_TOP_STORIES)
                return response.status_code == 200
        except Exception as e:
            logger.warning("HN health check failed", error=str(e))
            return False


__all__ = ["HackerNewsSource"]
