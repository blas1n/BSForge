"""Ruliweb (루리웹) community source collector.

Collects posts from Ruliweb boards.
https://bbs.ruliweb.com/
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.config.sources import RuliwebConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic
from app.services.collector.sources.korean_scraper_base import KoreanWebScraperBase

logger = get_logger(__name__)


class RuliwebSource(KoreanWebScraperBase, BaseSource[RuliwebConfig]):
    """Ruliweb community source collector.

    Fetches posts from Ruliweb boards.
    Inherits common Korean parsing utilities from KoreanWebScraperBase.

    Config options:
        boards: List of board IDs (e.g., ['best/humor', 'best/all'])
        limit: Maximum posts (default: 20)
        min_score: Minimum recommendation count (default: 10)

    Available boards:
        - best/humor: 유머 베스트
        - best/all: 전체 베스트
        - best/rulilife: 루리라이프 베스트
        - community/humor: 유머 게시판
        - community/rulilife: 루리라이프
    """

    _config: RuliwebConfig

    def __init__(
        self,
        config: RuliwebConfig,
        source_id: uuid.UUID,
    ):
        """Initialize Ruliweb source collector."""
        super().__init__(config, source_id)

    @property
    def source_name_kr(self) -> str:
        """Korean name of the source for logging and display."""
        return "루리웹"

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
            url = f"{base_url}/{board}"
            urls.append(url)

        return urls

    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse Ruliweb board list page.

        Args:
            soup: BeautifulSoup parsed HTML
            url: URL of the page

        Returns:
            List of post items
        """
        items: list[dict[str, Any]] = []

        # Find post rows
        posts = soup.select("tr.table_body")

        for post in posts:
            try:
                item = self._parse_post_item(post, url)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning("Failed to parse Ruliweb post", error=str(e))
                continue

        return items

    def _parse_post_item(self, post: Tag, list_url: str) -> dict[str, Any] | None:
        """Parse single post item from list.

        Args:
            post: BeautifulSoup Tag element for post
            list_url: URL of the list page

        Returns:
            Post data dict or None
        """
        # Get title and link
        title_elem = post.select_one("a.subject_link, a.deco")
        if not title_elem:
            return None

        # Get text, excluding nested spans (badges, etc.)
        title = title_elem.get_text(strip=True)
        # Clean up title by removing badge text at start
        title = re.sub(r"^(베|화|공|추)?\s*", "", title).strip()
        if not title:
            return None

        href_attr = title_elem.get("href", "")
        href = href_attr if isinstance(href_attr, str) else ""
        if not href:
            return None

        post_url = urljoin(str(self._config.base_url), href)

        # Get post ID from screen_out cell
        post_id_elem = post.select_one("td.id")
        post_id = None
        if post_id_elem:
            post_id = post_id_elem.get_text(strip=True)

        # Get recommendation count
        recommend_elem = post.select_one("td.recomd")
        recommends = 0
        if recommend_elem:
            rec_text = recommend_elem.get_text(strip=True)
            recommends = self._parse_number(rec_text)

        # Get view count
        view_elem = post.select_one("td.hit")
        views = 0
        if view_elem:
            view_text = view_elem.get_text(strip=True)
            views = self._parse_number(view_text)

        # Get comment count from title area
        comment_elem = post.select_one("span.num_reply, a.num_reply")
        comments = 0
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            comments = self._parse_number(comment_text)

        # Get author
        author_elem = post.select_one("td.writer, span.writer")
        author = author_elem.get_text(strip=True) if author_elem else None

        # Get date
        date_elem = post.select_one("td.time")
        published_at = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            published_at = self._parse_date(date_text)

        # Extract board from URL
        board = self._extract_board(list_url)

        return {
            "title": title,
            "url": post_url,
            "post_id": post_id,
            "score": recommends,
            "recommends": recommends,
            "views": views,
            "comments": comments,
            "author": author,
            "published_at": published_at,
            "board": board,
        }

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from various Ruliweb formats.

        Extends base class parsing with Ruliweb specific formats:
        - Time only "HH:MM" (interpreted as today)
        - Short year date "YY.MM.DD" (2-digit year)
        - Date with time "YY.MM.DD HH:MM"

        Args:
            text: Date text

        Returns:
            Datetime or None
        """
        # Try base class parsing first (Korean relative dates + standard formats)
        result = super()._parse_date(text)
        if result:
            return result

        if not text:
            return None

        text = text.strip()

        # Handle time only format "HH:MM" (today)
        if re.match(r"^\d{2}:\d{2}$", text):
            try:
                hour, minute = text.split(":")
                now = datetime.now(UTC)
                return now.replace(
                    hour=int(hour),
                    minute=int(minute),
                    second=0,
                    microsecond=0,
                )
            except (ValueError, IndexError):
                pass

        # Handle date format "YY.MM.DD" or "YY.MM.DD HH:MM"
        if "." in text:
            try:
                parts = text.split(".")
                if len(parts) >= 3:
                    year = int(parts[0])
                    if year < 100:
                        year += 2000
                    month = int(parts[1])
                    day = int(parts[2].split()[0])  # Handle "25.01.15 10:30" format
                    return datetime(year, month, day, tzinfo=UTC)
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
        # Match patterns like /best/humor, /community/humor
        match = re.search(r"/(best|community)/([^/?]+)", url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return "unknown"

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Extends base class conversion with Ruliweb specific fields:
        - post_id (글번호)
        - recommends (추천수)

        Args:
            item: Parsed item dict

        Returns:
            RawTopic or None
        """
        # Use base class for common conversion
        raw_topic = super()._to_raw_topic(item)
        if not raw_topic:
            return None

        # Add Ruliweb specific metrics
        if "recommends" in item:
            raw_topic.metrics["recommends"] = item["recommends"]

        # Add Ruliweb specific metadata
        if item.get("post_id"):
            raw_topic.metadata["post_id"] = item["post_id"]

        return raw_topic


__all__ = ["RuliwebSource"]
