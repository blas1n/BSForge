"""FM Korea (에펨코리아) community source collector.

Collects posts from FM Korea boards.
https://www.fmkorea.com/
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from app.config.sources import FmkoreaConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic
from app.services.collector.sources.web_scraper import WebScraperSource

logger = get_logger(__name__)


class FmkoreaSource(WebScraperSource, BaseSource[FmkoreaConfig]):
    """FM Korea community source collector.

    Fetches posts from FM Korea boards.

    Config options:
        boards: List of board IDs (e.g., ['best', 'humor', 'starfree'])
        limit: Maximum posts (default: 20)
        min_score: Minimum recommendation count (default: 10)

    Available boards:
        - best: 포텐 터짐 최신순
        - best2: 포텐 터짐 화제순
        - humor: 유머/움짤/이슈
        - starfree: 연예인잡담
        - girlgroup: 걸그룹
        - girlstar: 여자연예인
    """

    _config: FmkoreaConfig

    def __init__(
        self,
        config: FmkoreaConfig,
        source_id: uuid.UUID,
    ):
        """Initialize FM Korea source collector."""
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
            url = f"{base_url}/{board}"
            urls.append(url)

        return urls

    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse FM Korea board list page.

        Args:
            soup: BeautifulSoup parsed HTML
            url: URL of the page

        Returns:
            List of post items
        """
        items: list[dict[str, Any]] = []

        # Try best page format first (li.li elements)
        posts = soup.select("li.li")

        if posts:
            for post in posts:
                try:
                    item = self._parse_best_post_item(post, url)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning("Failed to parse FM Korea best post", error=str(e))
                    continue
        else:
            # Try table format (regular boards like starfree, girlgroup)
            table_posts = soup.select("table.bd_tb tbody tr:not(.notice)")

            for post in table_posts:
                try:
                    item = self._parse_table_post_item(post, url)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning("Failed to parse FM Korea table post", error=str(e))
                    continue

        return items

    def _parse_best_post_item(self, post: Tag, list_url: str) -> dict[str, Any] | None:
        """Parse single post item from best page (li.li format).

        Args:
            post: BeautifulSoup Tag element for post
            list_url: URL of the list page

        Returns:
            Post data dict or None
        """
        # Get title element
        title_elem = post.select_one("h3.title a, .title a")
        if not title_elem:
            return None

        # Get title text from ellipsis-target span
        title_span = title_elem.select_one("span.ellipsis-target")
        title = title_span.get_text(strip=True) if title_span else title_elem.get_text(strip=True)

        # Clean up title (remove comment count)
        title = re.sub(r"\s*\[\d+\]\s*$", "", title).strip()
        if not title:
            return None

        href_attr = title_elem.get("href", "")
        href = href_attr if isinstance(href_attr, str) else ""
        if not href:
            return None

        post_url = urljoin(str(self._config.base_url), href)

        # Extract post ID from URL
        post_id = None
        id_match = re.search(r"/(\d+)", href)
        if id_match:
            post_id = id_match.group(1)

        # Get recommendation count
        vote_elem = post.select_one("a.pc_voted_count span.count")
        recommends = 0
        if vote_elem:
            rec_text = vote_elem.get_text(strip=True)
            recommends = self._parse_number(rec_text)

        # Get comment count
        comment_elem = post.select_one("span.comment_count")
        comments = 0
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            comments = self._parse_number(comment_text)

        # Get author
        author_elem = post.select_one("span.author")
        author = None
        if author_elem:
            author = author_elem.get_text(strip=True)
            # Remove leading slash
            author = author.lstrip("/ ").strip()

        # Get date
        date_elem = post.select_one("span.regdate")
        published_at = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            published_at = self._parse_date(date_text)

        # Get category
        category_elem = post.select_one("span.category a")
        category = category_elem.get_text(strip=True) if category_elem else None

        # Extract board from URL
        board = self._extract_board(list_url)

        return {
            "title": title,
            "url": post_url,
            "post_id": post_id,
            "score": recommends,
            "recommends": recommends,
            "comments": comments,
            "author": author,
            "published_at": published_at,
            "board": board,
            "category": category,
        }

    def _parse_table_post_item(self, post: Tag, list_url: str) -> dict[str, Any] | None:
        """Parse single post item from table format (regular boards).

        Args:
            post: BeautifulSoup Tag element for post row
            list_url: URL of the list page

        Returns:
            Post data dict or None
        """
        # Get title cell
        title_cell = post.select_one("td.title")
        if not title_cell:
            return None

        # Get title link
        title_elem = title_cell.select_one("a:not(.replyNum)")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        href_attr = title_elem.get("href", "")
        href = href_attr if isinstance(href_attr, str) else ""
        if not href:
            return None

        post_url = urljoin(str(self._config.base_url), href)

        # Extract post ID from URL
        post_id = None
        id_match = re.search(r"/(\d+)", href)
        if id_match:
            post_id = id_match.group(1)

        # Get recommendation count
        vote_cell = post.select_one("td.m_no_voted")
        recommends = 0
        if vote_cell:
            rec_text = vote_cell.get_text(strip=True)
            if rec_text and rec_text != "&nbsp;":
                recommends = self._parse_number(rec_text)

        # Get view count
        view_cells = post.select("td.m_no")
        views = 0
        if len(view_cells) >= 1:
            view_text = view_cells[0].get_text(strip=True)
            views = self._parse_number(view_text)

        # Get comment count
        comment_elem = title_cell.select_one("a.replyNum")
        comments = 0
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            comments = self._parse_number(comment_text)

        # Get author
        author_cell = post.select_one("td.author")
        author = None
        if author_cell:
            author_link = author_cell.select_one("a")
            if author_link:
                author = author_link.get_text(strip=True)
            else:
                author = author_cell.get_text(strip=True)

        # Get date
        date_cell = post.select_one("td.time")
        published_at = None
        if date_cell:
            date_text = date_cell.get_text(strip=True)
            published_at = self._parse_date(date_text)

        # Get category
        category_cell = post.select_one("td.cate a")
        category = category_cell.get_text(strip=True) if category_cell else None

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
            "category": category,
        }

    def _parse_number(self, text: str) -> int:
        """Parse number from text.

        Args:
            text: Text containing number

        Returns:
            Parsed integer
        """
        if not text:
            return 0

        text = text.strip()

        # Remove brackets and other characters
        try:
            return int(re.sub(r"[^\d]", "", text))
        except ValueError:
            return 0

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from various formats.

        Args:
            text: Date text (e.g., "2 분 전", "3 시간 전", "17:55")

        Returns:
            Datetime or None
        """
        if not text:
            return None

        text = text.strip()

        # Handle relative times
        if "분 전" in text:
            try:
                match = re.search(r"(\d+)", text)
                if match:
                    minutes = int(match.group(1))
                    return datetime.now(UTC) - timedelta(minutes=minutes)
            except (AttributeError, ValueError):
                pass

        if "시간 전" in text:
            try:
                match = re.search(r"(\d+)", text)
                if match:
                    hours = int(match.group(1))
                    return datetime.now(UTC) - timedelta(hours=hours)
            except (AttributeError, ValueError):
                pass

        if "일 전" in text:
            try:
                match = re.search(r"(\d+)", text)
                if match:
                    days = int(match.group(1))
                    return datetime.now(UTC) - timedelta(days=days)
            except (AttributeError, ValueError):
                pass

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

        # Handle date format "YY.MM.DD" or "MM.DD"
        if "." in text:
            try:
                parts = text.split(".")
                now = datetime.now(UTC)
                if len(parts) == 3:
                    year = int(parts[0])
                    if year < 100:
                        year += 2000
                    month = int(parts[1])
                    day = int(parts[2])
                    return datetime(year, month, day, tzinfo=UTC)
                elif len(parts) == 2:
                    month = int(parts[0])
                    day = int(parts[1])
                    return datetime(now.year, month, day, tzinfo=UTC)
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
        # Match patterns like /best, /humor
        match = re.search(r"fmkorea\.com/([^/?]+)", url)
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
                    "recommends": item.get("recommends", 0),
                    "comments": item.get("comments", 0),
                    "score": item.get("score", 0),
                },
                metadata={
                    "post_id": item.get("post_id"),
                    "board": item.get("board"),
                    "category": item.get("category"),
                    "author": item.get("author"),
                    "source_name": "FM코리아",
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to convert FM Korea post",
                title=item.get("title", "")[:50],
                error=str(e),
            )
            return None


__all__ = ["FmkoreaSource"]
