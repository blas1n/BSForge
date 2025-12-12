"""Clien community source collector.

Collects posts from Clien (클리앙) boards.
https://www.clien.net/
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.config.sources import ClienConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic
from app.services.collector.sources.web_scraper import WebScraperSource

logger = get_logger(__name__)


class ClienSource(WebScraperSource, BaseSource[ClienConfig]):
    """Clien community source collector.

    Fetches posts from Clien boards.

    Config options:
        boards: List of board IDs (e.g., ['cm_ittalk', 'cm_tech'])
        limit: Maximum posts (default: 20)
        min_score: Minimum view count (default: 500)

    Available boards:
        - cm_ittalk: IT수다
        - cm_tech: 테크
        - park: 모두의공원
        - jirum: 알뜰구매
        - cm_car: 자동차
        - cm_finance: 재테크
    """

    _config: ClienConfig

    def __init__(
        self,
        config: ClienConfig,
        source_id: uuid.UUID,
    ):
        """Initialize Clien source collector."""
        super().__init__(config, source_id)

    def _get_list_urls(self, base_url: str, params: dict[str, Any]) -> list[str]:
        """Get list URLs for configured boards.

        Args:
            base_url: Base URL
            params: Collection parameters

        Returns:
            List of board URLs to scrape
        """
        boards = params.get("boards", self._config.boards)

        urls = []
        for board in boards:
            url = f"{base_url}/service/board/{board}"
            urls.append(url)

        return urls

    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse Clien board list page.

        Args:
            soup: BeautifulSoup parsed HTML
            url: URL of the page

        Returns:
            List of post items
        """
        items: list[dict[str, Any]] = []

        # Find post list items
        posts = soup.select("div.list_item")

        for post in posts:
            try:
                item = self._parse_post_item(post, url)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning("Failed to parse Clien post", error=str(e))
                continue

        return items

    def _parse_post_item(self, post: BeautifulSoup, list_url: str) -> dict[str, Any] | None:
        """Parse single post item from list.

        Args:
            post: BeautifulSoup element for post
            list_url: URL of the list page

        Returns:
            Post data dict or None
        """
        # Get title and link
        title_elem = post.select_one(".list_subject, .subject_fixed")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        # Get link - might be in anchor or parent
        link_elem = title_elem if title_elem.name == "a" else title_elem.find("a")
        if not link_elem:
            link_elem = post.select_one("a.list_subject")

        href = link_elem.get("href", "") if link_elem else ""
        if not href:
            return None

        post_url = urljoin(self._config.base_url, href)

        # Get view count (score)
        view_elem = post.select_one(".view_count, .hit")
        views = 0
        if view_elem:
            view_text = view_elem.get_text(strip=True)
            # Parse numbers like "1.2k" or "1234"
            views = self._parse_number(view_text)

        # Get comment count
        comment_elem = post.select_one(".rSymph05, .comment_count")
        comments = 0
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            comments = self._parse_number(comment_text)

        # Get author
        author_elem = post.select_one(".nickname, .author")
        author = author_elem.get_text(strip=True) if author_elem else None

        # Get date
        date_elem = post.select_one(".timestamp, .time")
        published_at = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            published_at = self._parse_date(date_text)

        # Extract board from URL
        board = self._extract_board(list_url)

        return {
            "title": title,
            "url": post_url,
            "score": views,
            "views": views,
            "comments": comments,
            "author": author,
            "published_at": published_at,
            "board": board,
        }

    def _parse_number(self, text: str) -> int:
        """Parse number from text (handles 'k' suffix).

        Args:
            text: Text containing number

        Returns:
            Parsed integer
        """
        if not text:
            return 0

        text = text.strip().lower()

        # Handle "1.2k" format
        if "k" in text:
            try:
                num = float(text.replace("k", "").replace(",", ""))
                return int(num * 1000)
            except ValueError:
                return 0

        # Handle regular numbers
        try:
            return int(re.sub(r"[^\d]", "", text))
        except ValueError:
            return 0

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from various formats.

        Args:
            text: Date text

        Returns:
            Datetime or None
        """
        if not text:
            return None

        text = text.strip()

        # Handle relative times like "1시간 전", "방금"
        if "방금" in text or "초 전" in text:
            return datetime.now(UTC)
        if "분 전" in text:
            try:
                minutes = int(re.search(r"(\d+)", text).group(1))
                from datetime import timedelta

                return datetime.now(UTC) - timedelta(minutes=minutes)
            except (AttributeError, ValueError):
                return datetime.now(UTC)
        if "시간 전" in text:
            try:
                hours = int(re.search(r"(\d+)", text).group(1))
                from datetime import timedelta

                return datetime.now(UTC) - timedelta(hours=hours)
            except (AttributeError, ValueError):
                return datetime.now(UTC)

        # Handle date formats like "2024-01-15", "01-15"
        try:
            # Try full date
            if len(text) >= 10:
                return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
            # Try month-day (assume current year)
            if "-" in text or "." in text:
                sep = "-" if "-" in text else "."
                parts = text.split(sep)
                if len(parts) >= 2:
                    month = int(parts[0])
                    day = int(parts[1])
                    return datetime(datetime.now(UTC).year, month, day, tzinfo=UTC)
        except (ValueError, IndexError):
            pass

        return None

    def _extract_board(self, url: str) -> str:
        """Extract board ID from URL.

        Args:
            url: Board URL

        Returns:
            Board ID or 'unknown'
        """
        match = re.search(r"/board/([^/?]+)", url)
        return match.group(1) if match else "unknown"

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Args:
            item: Parsed item dict

        Returns:
            RawTopic or None
        """
        try:
            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(item["url"]),
                title=item["title"],
                content=None,
                published_at=item.get("published_at"),
                metrics={
                    "views": item.get("views", 0),
                    "comments": item.get("comments", 0),
                    "score": item.get("score", 0),
                },
                metadata={
                    "board": item.get("board"),
                    "author": item.get("author"),
                    "source_name": "클리앙",
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to convert Clien post",
                title=item.get("title", "")[:50],
                error=str(e),
            )
            return None


__all__ = ["ClienSource"]
