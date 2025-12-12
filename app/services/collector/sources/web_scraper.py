"""Generic web scraper base class.

Provides common functionality for HTML scraping sources.
Subclasses implement site-specific parsing logic.
"""

import asyncio
import uuid
from abc import abstractmethod
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.config.sources import WebScraperConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

logger = get_logger(__name__)


class WebScraperSource(BaseSource[WebScraperConfig]):
    """Base class for HTML scraping sources.

    Provides common functionality like:
    - Rate limiting
    - HTML fetching and parsing
    - Error handling
    - User-Agent rotation

    Subclasses must implement:
    - _parse_list_page(): Extract items from list page
    - _to_raw_topic(): Convert item to RawTopic

    Config options:
        base_url: Base URL for the website
        name: Display name for the source
        limit: Maximum items to scrape (default: 20)
        min_score: Minimum score threshold (default: 0)
        request_timeout: HTTP timeout (default: 15s)
        rate_limit_delay: Delay between requests (default: 1s)
    """

    def __init__(
        self,
        config: WebScraperConfig,
        source_id: uuid.UUID,
    ):
        """Initialize web scraper source.

        Args:
            config: Typed configuration object
            source_id: UUID of the source
        """
        super().__init__(config, source_id)

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for requests.

        Returns:
            Headers dict with User-Agent
        """
        return {
            "User-Agent": self._config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Fetch HTML content from URL.

        Args:
            client: HTTP client
            url: URL to fetch

        Returns:
            HTML content or None if fetch failed
        """
        try:
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch URL", url=url, error=str(e))
            return None

    async def _rate_limit(self) -> None:
        """Apply rate limiting delay."""
        if self._config.rate_limit_delay > 0:
            await asyncio.sleep(self._config.rate_limit_delay)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect topics by scraping web pages.

        Args:
            params: Optional parameters to override defaults

        Returns:
            List of RawTopic from scraped pages
        """
        params = params or {}
        base_url = self._config.base_url
        name = self._config.name
        limit = params.get("limit", self._config.limit)
        min_score = params.get("min_score", self._config.min_score)

        if not base_url:
            logger.error("No base_url configured for scraper", source_name=name)
            return []

        logger.info(
            "Collecting from web scraper",
            source_name=name,
            base_url=base_url,
            limit=limit,
        )

        topics: list[RawTopic] = []

        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout, follow_redirects=True
            ) as client:
                # Get list page URLs to scrape
                list_urls = self._get_list_urls(base_url, params)

                for list_url in list_urls:
                    if len(topics) >= limit:
                        break

                    html = await self._fetch_html(client, list_url)
                    if not html:
                        continue

                    soup = BeautifulSoup(html, "html.parser")
                    items = self._parse_list_page(soup, list_url)

                    for item in items:
                        if len(topics) >= limit:
                            break

                        # Check minimum score
                        score = item.get("score", 0)
                        if score < min_score:
                            continue

                        topic = self._to_raw_topic(item)
                        if topic:
                            topics.append(topic)

                    await self._rate_limit()

        except Exception as e:
            logger.error(
                "Scraper collection failed",
                source_name=name,
                error=str(e),
                exc_info=True,
            )

        logger.info(
            "Scraper collection complete",
            source_name=name,
            collected=len(topics),
        )
        return topics

    def _get_list_urls(self, base_url: str, params: dict[str, Any]) -> list[str]:
        """Get list of URLs to scrape.

        Override in subclass for pagination or multiple boards.

        Args:
            base_url: Base URL from config
            params: Collection parameters

        Returns:
            List of URLs to scrape
        """
        return [base_url]

    @abstractmethod
    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse list page HTML to extract items.

        Must be implemented by subclass.

        Args:
            soup: BeautifulSoup parsed HTML
            url: URL of the page

        Returns:
            List of item dicts with at least 'title' and 'url' keys
        """
        pass

    @abstractmethod
    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic.

        Must be implemented by subclass.

        Args:
            item: Parsed item dict from _parse_list_page

        Returns:
            RawTopic or None if conversion failed
        """
        pass

    async def health_check(self) -> bool:
        """Check if website is accessible.

        Returns:
            True if website responds successfully
        """
        base_url = self._config.base_url
        if not base_url:
            return False

        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout, follow_redirects=True
            ) as client:
                response = await client.get(base_url, headers=self._get_headers())
                return response.status_code == 200
        except Exception as e:
            logger.warning(
                "Scraper health check failed",
                base_url=base_url,
                error=str(e),
            )
            return False


__all__ = ["WebScraperSource"]
