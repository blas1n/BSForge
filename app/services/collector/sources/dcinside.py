"""DC Inside (디시인사이드) source collector.

Collects posts from DC Inside galleries.
https://www.dcinside.com/
"""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.config.sources import DCInsideConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic
from app.services.collector.sources.korean_scraper_base import KoreanWebScraperBase

logger = get_logger(__name__)


class DCInsideSource(KoreanWebScraperBase, BaseSource[DCInsideConfig]):
    """DC Inside gallery source collector.

    Fetches posts from DC Inside galleries (major, minor, mini).
    Inherits common Korean parsing utilities from KoreanWebScraperBase.

    Config options:
        galleries: List of gallery IDs (e.g., ['programming', 'ai'])
        gallery_type: Type of gallery ('major', 'minor', 'mini')
        limit: Maximum posts (default: 20)
        min_score: Minimum recommendation count (default: 10)

    Popular galleries:
        Major:
        - programming: 프로그래밍
        - github: Github
        - baseball_new9: 야구

        Minor:
        - ai_gallery: AI
        - bigdata: 빅데이터
        - stockus: 미국주식
    """

    # Scoped source: requires channel-specific galleries
    is_global = False

    _config: DCInsideConfig

    @classmethod
    def build_config(cls, overrides: dict[str, Any]) -> DCInsideConfig:
        """Build DCInsideConfig from channel overrides.

        Args:
            overrides: Configuration overrides with optional keys:
                - params.galleries: List of gallery IDs (optional)
                - params.gallery_type: Gallery type (optional)
                - filters.min_score: Minimum score (optional)
                - limit: Maximum posts (optional)

        Returns:
            DCInsideConfig instance
        """
        params = overrides.get("params", {})
        filters = overrides.get("filters", {})
        return DCInsideConfig(
            galleries=params.get("galleries", ["programming"]),
            gallery_type=params.get("gallery_type", "major"),
            min_score=filters.get("min_score", 10),
            limit=overrides.get("limit", 20),
        )

    @property
    def source_name_kr(self) -> str:
        """Korean name of the source for logging and display."""
        return "디시인사이드"

    def _get_list_urls(self, base_url: str, params: dict[str, Any]) -> list[str]:
        """Get list URLs for configured galleries.

        Args:
            base_url: Base URL from config
            params: Collection parameters

        Returns:
            List of gallery URLs to scrape
        """
        galleries = params.get("galleries", self._config.galleries)
        gallery_type = params.get("gallery_type", self._config.gallery_type)

        # Determine URL path based on gallery type
        if gallery_type == "minor":
            gallery_path = "/mgallery/board/lists"
        elif gallery_type == "mini":
            gallery_path = "/mini/board/lists"
        else:
            gallery_path = "/board/lists"

        urls = []
        for gallery in galleries:
            url = f"{base_url}{gallery_path}/?id={gallery}"
            urls.append(url)

        return urls

    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse DC Inside gallery list page.

        Args:
            soup: BeautifulSoup parsed HTML
            url: URL of the page

        Returns:
            List of post items
        """
        items: list[dict[str, Any]] = []

        # Find post table rows
        posts = soup.select("tr.ub-content")

        for post in posts:
            try:
                item = self._parse_post_item(post, url)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning("Failed to parse DC Inside post", error=str(e))
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
        # Skip notice posts
        if post.get("data-type") == "icon_notice":
            return None

        # Get post number
        post_num_elem = post.select_one(".gall_num")
        if not post_num_elem:
            return None

        post_num = post_num_elem.get_text(strip=True)
        # Skip non-numeric posts (notices, ads)
        if not post_num.isdigit():
            return None

        # Get title
        title_elem = post.select_one(".gall_tit a:first-child")
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

        # Get recommendation count (score)
        recommend_elem = post.select_one(".gall_recommend")
        recommends = 0
        if recommend_elem:
            rec_text = recommend_elem.get_text(strip=True)
            recommends = self._parse_number(rec_text)

        # Get view count
        view_elem = post.select_one(".gall_count")
        views = 0
        if view_elem:
            view_text = view_elem.get_text(strip=True)
            views = self._parse_number(view_text)

        # Get comment count
        comment_elem = post.select_one(".gall_tit .reply_num")
        comments = 0
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            # Format is usually "[123]"
            comments = self._parse_number(comment_text)

        # Get author
        author_elem = post.select_one(".gall_writer .nickname, .gall_writer em")
        author = author_elem.get_text(strip=True) if author_elem else None

        # Get date
        date_elem = post.select_one(".gall_date")
        published_at = None
        if date_elem:
            title_attr = date_elem.get("title", "")
            date_text = (
                title_attr if isinstance(title_attr, str) else date_elem.get_text(strip=True)
            )
            published_at = self._parse_date(date_text)

        # Extract gallery from URL
        gallery = self._extract_gallery(list_url)

        return {
            "title": title,
            "url": post_url,
            "post_num": post_num,
            "score": recommends,
            "recommends": recommends,
            "views": views,
            "comments": comments,
            "author": author,
            "published_at": published_at,
            "gallery": gallery,
        }

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from various DC Inside formats.

        Extends base class parsing with DC Inside specific formats:
        - Time only "14:30" (interpreted as today)
        - Short date "01.15" (interpreted as current year)

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

        # Handle time only format "14:30" (today)
        if ":" in text and len(text) <= 5:
            try:
                time_parts = text.split(":")
                now = datetime.now(UTC)
                return now.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=0,
                    microsecond=0,
                )
            except (ValueError, IndexError):
                pass

        # Handle date format "01.15" (current year)
        if "." in text and len(text) <= 5:
            try:
                date_parts = text.split(".")
                now = datetime.now(UTC)
                return datetime(
                    now.year,
                    int(date_parts[0]),
                    int(date_parts[1]),
                    tzinfo=UTC,
                )
            except (ValueError, IndexError):
                pass

        return None

    def _extract_gallery(self, url: str) -> str:
        """Extract gallery ID from URL.

        Args:
            url: Gallery URL

        Returns:
            Gallery ID or 'unknown'
        """
        match = re.search(r"id=([^&]+)", url)
        return match.group(1) if match else "unknown"

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Extends base class conversion with DC Inside specific fields:
        - recommends (추천수)
        - post_num (글번호)
        - gallery (갤러리)

        Args:
            item: Parsed item dict

        Returns:
            RawTopic or None
        """
        # Use base class for common conversion
        raw_topic = super()._to_raw_topic(item)
        if not raw_topic:
            return None

        # Add DC Inside specific metrics (recommends is separate from score)
        if "recommends" in item:
            raw_topic.metrics["recommends"] = item["recommends"]

        # Add DC Inside specific metadata
        if item.get("post_num"):
            raw_topic.metadata["post_num"] = item["post_num"]
        if item.get("gallery"):
            raw_topic.metadata["gallery"] = item["gallery"]

        return raw_topic


__all__ = ["DCInsideSource"]
