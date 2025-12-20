"""Korean community web scraper base class.

Provides shared functionality for Korean community scrapers:
- Number parsing (1.2k, 1,234 formats)
- Korean relative date parsing (분 전, 시간 전, etc.)
- Common RawTopic conversion

This reduces code duplication across Clien, DCInside, FMKorea, Ruliweb.
"""

import re
from abc import abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import HttpUrl

from app.core.logging import get_logger
from app.services.collector.base import RawTopic
from app.services.collector.sources.web_scraper import WebScraperSource

logger = get_logger(__name__)


class KoreanWebScraperBase(WebScraperSource):
    """Base class for Korean community web scrapers.

    Provides common functionality for Korean sites like:
    - Clien (클리앙)
    - DCInside (디시인사이드)
    - FMKorea (에펨코리아)
    - Ruliweb (루리웹)

    Subclasses must implement:
    - source_name_kr: Korean name for logging
    - _parse_list_page(): Site-specific HTML parsing
    - _get_list_urls(): URL generation for boards

    Optional overrides:
    - _to_raw_topic(): If site needs custom conversion
    """

    @property
    @abstractmethod
    def source_name_kr(self) -> str:
        """Korean name of the source (e.g., '클리앙', 'FM코리아').

        Used for logging and display.
        """
        pass

    def _parse_number(self, text: str) -> int:
        """Parse number from text (handles Korean formats).

        Supported formats:
        - Regular numbers: "1234", "1,234"
        - K suffix: "1.2k", "1.2K" -> 1200
        - 만 suffix: "1.2만" -> 12000

        Args:
            text: Text containing number

        Returns:
            Parsed integer, 0 if parsing fails
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

        # Handle "1.2만" format
        if "만" in text:
            try:
                num = float(text.replace("만", "").replace(",", ""))
                return int(num * 10000)
            except ValueError:
                return 0

        # Handle regular numbers with commas
        try:
            return int(re.sub(r"[^\d]", "", text))
        except ValueError:
            return 0

    def _parse_korean_relative_date(self, text: str) -> datetime | None:
        """Parse Korean relative date expressions.

        Supported formats:
        - "방금", "방금 전" -> now
        - "N초 전" -> now - N seconds
        - "N분 전" -> now - N minutes
        - "N시간 전" -> now - N hours
        - "N일 전" -> now - N days
        - "어제" -> yesterday
        - "그저께" -> day before yesterday

        Args:
            text: Korean date text

        Returns:
            Datetime or None if not a relative format
        """
        if not text:
            return None

        text = text.strip()
        now = datetime.now(UTC)

        # Immediate time
        if "방금" in text:
            return now

        # Seconds ago
        if "초 전" in text or "초전" in text:
            match = re.search(r"(\d+)", text)
            if match:
                seconds = int(match.group(1))
                return now - timedelta(seconds=seconds)
            return now

        # Minutes ago
        if "분 전" in text or "분전" in text:
            match = re.search(r"(\d+)", text)
            if match:
                minutes = int(match.group(1))
                return now - timedelta(minutes=minutes)
            return now

        # Hours ago
        if "시간 전" in text or "시간전" in text:
            match = re.search(r"(\d+)", text)
            if match:
                hours = int(match.group(1))
                return now - timedelta(hours=hours)
            return now

        # Days ago
        if "일 전" in text or "일전" in text:
            match = re.search(r"(\d+)", text)
            if match:
                days = int(match.group(1))
                return now - timedelta(days=days)
            return now

        # Yesterday
        if "어제" in text:
            return now - timedelta(days=1)

        # Day before yesterday
        if "그저께" in text or "그제" in text:
            return now - timedelta(days=2)

        return None

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from various formats.

        Tries Korean relative dates first, then common date formats.

        Args:
            text: Date text

        Returns:
            Datetime or None if parsing fails
        """
        if not text:
            return None

        text = text.strip()

        # Try Korean relative date first
        relative_date = self._parse_korean_relative_date(text)
        if relative_date:
            return relative_date

        # Try common date formats
        date_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%m-%d %H:%M",
            "%m-%d",
            "%m.%d %H:%M",
            "%m.%d",
        ]

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(text, fmt)  # noqa: DTZ007
                # Add current year if not present
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now(UTC).year)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue

        return None

    def _extract_board(self, url: str) -> str | None:
        """Extract board identifier from URL.

        Override in subclass for site-specific URL patterns.

        Args:
            url: List page URL

        Returns:
            Board identifier or None
        """
        return None

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Standard implementation for Korean community sites.
        Override if site needs custom conversion.

        Args:
            item: Parsed item dict with keys:
                - title (required)
                - url (required)
                - score (optional, default 0)
                - comments (optional)
                - author (optional)
                - published_at (optional)
                - board (optional)

        Returns:
            RawTopic or None if required fields missing
        """
        title = item.get("title")
        url = item.get("url")

        if not title or not url:
            return None

        # Build content from available fields
        content_parts = []
        if item.get("author"):
            content_parts.append(f"작성자: {item['author']}")
        if item.get("board"):
            content_parts.append(f"게시판: {item['board']}")
        content = " | ".join(content_parts) if content_parts else None

        # Build metrics
        metrics: dict[str, Any] = {}
        if "score" in item:
            metrics["score"] = item["score"]
        if "views" in item:
            metrics["views"] = item["views"]
        if "comments" in item:
            metrics["comments"] = item["comments"]
        if "likes" in item:
            metrics["likes"] = item["likes"]

        # Build metadata
        metadata: dict[str, Any] = {
            "source_name": self.source_name_kr,
        }
        if item.get("author"):
            metadata["author"] = item["author"]
        if item.get("board"):
            metadata["board"] = item["board"]

        return RawTopic(
            source_id=str(self.source_id),
            title=title,
            content=content,
            source_url=HttpUrl(url),
            published_at=item.get("published_at"),
            metrics=metrics if metrics else {},
            metadata=metadata,
        )


__all__ = ["KoreanWebScraperBase"]
