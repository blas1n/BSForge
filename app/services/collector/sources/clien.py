"""Clien community source collector.

Collects posts from Clien (클리앙) boards.
https://www.clien.net/
"""

import re
import uuid
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.config.sources import ClienConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic
from app.services.collector.sources.korean_scraper_base import KoreanWebScraperBase

logger = get_logger(__name__)


class ClienSource(KoreanWebScraperBase, BaseSource[ClienConfig]):
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

    @property
    def source_name_kr(self) -> str:
        """Korean name of the source."""
        return "클리앙"

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

    def _parse_post_item(self, post: Tag, list_url: str) -> dict[str, Any] | None:
        """Parse single post item from list.

        Args:
            post: BeautifulSoup Tag element for post
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

        href = ""
        if link_elem and isinstance(link_elem, Tag):
            href_attr = link_elem.get("href", "")
            href = href_attr if isinstance(href_attr, str) else ""
        if not href:
            return None

        post_url = urljoin(str(self._config.base_url), href)

        # Get view count (score)
        view_elem = post.select_one(".view_count, .hit")
        views = 0
        if view_elem:
            view_text = view_elem.get_text(strip=True)
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

    def _extract_board(self, url: str) -> str | None:
        """Extract board ID from URL.

        Args:
            url: Board URL

        Returns:
            Board ID or None
        """
        match = re.search(r"/board/([^/?]+)", url)
        return match.group(1) if match else None

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Uses base class conversion. Clien doesn't have any special fields
        beyond the standard Korean community format.

        Args:
            item: Parsed item dict

        Returns:
            RawTopic or None
        """
        # Use base class for common conversion
        # Clien follows the standard pattern with views, comments, score, board
        return super()._to_raw_topic(item)


__all__ = ["ClienSource"]
