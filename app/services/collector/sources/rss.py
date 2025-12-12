"""RSS/Atom feed source collector.

Generic collector for RSS and Atom feeds.
Uses feedparser for parsing various feed formats.
"""

import uuid
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from pydantic import HttpUrl

from app.config.sources import RSSConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

logger = get_logger(__name__)


class RSSSource(BaseSource[RSSConfig]):
    """RSS/Atom feed source collector.

    Fetches and parses RSS/Atom feeds from any URL.

    Config options:
        feed_url: URL of the RSS/Atom feed
        limit: Maximum entries to fetch (default: 20)
        name: Display name for the source

    Params override (from channel config):
        limit: Override entry limit
    """

    def __init__(
        self,
        config: RSSConfig,
        source_id: uuid.UUID,
    ):
        """Initialize RSS source collector.

        Args:
            config: Typed configuration object
            source_id: UUID of the source
        """
        super().__init__(config, source_id)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect entries from RSS/Atom feed.

        Args:
            params: Optional parameters to override defaults

        Returns:
            List of RawTopic from feed
        """
        params = params or {}
        feed_url = self._config.feed_url
        limit = params.get("limit", self._config.limit)
        source_name = self._config.name

        if not feed_url:
            logger.error("No feed_url configured for RSS source")
            return []

        logger.info(
            "Collecting from RSS feed",
            feed_url=feed_url,
            source_name=source_name,
            limit=limit,
        )

        try:
            # Fetch feed content
            async with httpx.AsyncClient(timeout=self._config.request_timeout) as client:
                response = await client.get(feed_url)
                response.raise_for_status()
                content = response.text

            # Parse feed
            feed = feedparser.parse(content)

            if feed.bozo and feed.bozo_exception:
                logger.warning(
                    "Feed parsing had issues",
                    feed_url=feed_url,
                    error=str(feed.bozo_exception),
                )

            # Convert entries to topics
            topics: list[RawTopic] = []
            for entry in feed.entries[:limit]:
                topic = self._to_raw_topic(entry, source_name)
                if topic:
                    topics.append(topic)

            logger.info(
                "RSS collection complete",
                source_name=source_name,
                collected=len(topics),
                total_entries=len(feed.entries),
            )
            return topics

        except httpx.HTTPError as e:
            logger.error("RSS feed fetch failed", feed_url=feed_url, error=str(e))
            raise
        except Exception as e:
            logger.error("RSS collection failed", feed_url=feed_url, error=str(e), exc_info=True)
            raise

    def _to_raw_topic(self, entry: Any, source_name: str) -> RawTopic | None:
        """Convert feed entry to RawTopic.

        Args:
            entry: feedparser entry object
            source_name: Name of the RSS source

        Returns:
            RawTopic or None if conversion failed
        """
        try:
            # Get URL - prefer link, fall back to id
            url = entry.get("link") or entry.get("id")
            if not url:
                logger.warning("RSS entry has no URL", title=entry.get("title", "")[:50])
                return None

            # Get title
            title = entry.get("title")
            if not title:
                logger.warning("RSS entry has no title", url=url)
                return None

            # Get content/summary
            content = None
            if entry.get("content"):
                # Atom feeds have content as list
                content = entry.content[0].get("value", "") if entry.content else None
            elif entry.get("summary"):
                content = entry.summary
            elif entry.get("description"):
                content = entry.description

            # Strip HTML tags from content (basic)
            if content:
                content = self._strip_html(content)

            # Parse published date
            published_at = self._parse_date(entry)

            # Get author
            author = entry.get("author") or entry.get("dc_creator")

            # Get categories/tags
            tags = []
            if entry.get("tags"):
                tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]

            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(url),
                title=title,
                content=content,
                published_at=published_at,
                metrics={},  # RSS feeds typically don't have engagement metrics
                metadata={
                    "source_name": source_name,
                    "author": author,
                    "tags": tags,
                    "feed_id": entry.get("id"),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to convert RSS entry",
                title=entry.get("title", "")[:50],
                error=str(e),
            )
            return None

    def _parse_date(self, entry: Any) -> datetime | None:
        """Parse date from feed entry.

        Args:
            entry: feedparser entry

        Returns:
            Datetime or None if parsing failed
        """
        # Try different date fields
        date_fields = ["published_parsed", "updated_parsed", "created_parsed"]

        for field in date_fields:
            parsed = entry.get(field)
            if parsed:
                try:
                    # feedparser returns time.struct_time
                    return datetime(*parsed[:6], tzinfo=UTC)
                except Exception:
                    continue

        # Try string dates
        date_str_fields = ["published", "updated", "created"]
        for field in date_str_fields:
            date_str = entry.get(field)
            if date_str:
                try:
                    return parsedate_to_datetime(date_str)
                except Exception:
                    continue

        return None

    def _strip_html(self, text: str) -> str:
        """Basic HTML tag stripping.

        Args:
            text: Text with potential HTML

        Returns:
            Text with HTML tags removed
        """
        import re

        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", "", text)
        # Decode common entities
        clean = clean.replace("&nbsp;", " ")
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = clean.replace("&quot;", '"')
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    async def health_check(self) -> bool:
        """Check if RSS feed is accessible.

        Returns:
            True if feed responds successfully
        """
        feed_url = self._config.feed_url
        if not feed_url:
            return False

        try:
            async with httpx.AsyncClient(timeout=self._config.request_timeout) as client:
                response = await client.get(feed_url)
                return response.status_code == 200
        except Exception as e:
            logger.warning("RSS health check failed", feed_url=feed_url, error=str(e))
            return False


__all__ = ["RSSSource"]
