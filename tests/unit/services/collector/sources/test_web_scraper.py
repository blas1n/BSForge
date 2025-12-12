"""Unit tests for WebScraperSource base class.

Tests use mocked HTTP responses and a concrete test implementation.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from app.config.sources import WebScraperConfig
from app.services.collector.base import RawTopic
from app.services.collector.sources.web_scraper import WebScraperSource


class ConcreteWebScraper(WebScraperSource):
    """Concrete implementation for testing."""

    def _parse_list_page(self, soup: BeautifulSoup, url: str) -> list[dict[str, Any]]:
        """Parse list page HTML."""
        items = []
        for article in soup.find_all("article"):
            title_elem = article.find("h2")
            link_elem = article.find("a")
            score_elem = article.find("span", class_="score")

            if title_elem and link_elem:
                items.append(
                    {
                        "title": title_elem.get_text(strip=True),
                        "url": link_elem.get("href"),
                        "score": int(score_elem.get_text()) if score_elem else 0,
                    }
                )
        return items

    def _to_raw_topic(self, item: dict[str, Any]) -> RawTopic | None:
        """Convert parsed item to RawTopic."""
        from datetime import UTC, datetime

        from pydantic import HttpUrl

        try:
            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(item["url"]),
                title=item["title"],
                content=None,
                published_at=datetime.now(UTC),
                metrics={"score": item.get("score", 0)},
                metadata={},
            )
        except Exception:
            return None


@pytest.fixture
def source_id() -> uuid.UUID:
    """Create a test source UUID."""
    return uuid.uuid4()


@pytest.fixture
def web_scraper(source_id: uuid.UUID) -> ConcreteWebScraper:
    """Create a web scraper with test config."""
    config = WebScraperConfig(
        base_url="https://example.com/articles",
        name="Test Scraper",
        limit=10,
        min_score=5,
    )
    return ConcreteWebScraper(config=config, source_id=source_id)


@pytest.fixture
def mock_html() -> str:
    """Create mock HTML content."""
    return """
    <html>
    <body>
        <article>
            <h2>First Article Title</h2>
            <a href="https://example.com/article/1">Link</a>
            <span class="score">100</span>
        </article>
        <article>
            <h2>Second Article Title</h2>
            <a href="https://example.com/article/2">Link</a>
            <span class="score">50</span>
        </article>
        <article>
            <h2>Low Score Article</h2>
            <a href="https://example.com/article/3">Link</a>
            <span class="score">2</span>
        </article>
    </body>
    </html>
    """


class TestWebScraperCollect:
    """Tests for WebScraperSource.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_success(self, web_scraper: ConcreteWebScraper, mock_html: str):
        """Test successful collection of articles."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            topics = await web_scraper.collect()

            # Should have 2 articles (one filtered by min_score)
            assert len(topics) == 2
            assert topics[0].title == "First Article Title"
            assert topics[0].metrics["score"] == 100

    @pytest.mark.asyncio
    async def test_collect_respects_limit(self, web_scraper: ConcreteWebScraper, mock_html: str):
        """Test that collection respects limit parameter."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            topics = await web_scraper.collect(params={"limit": 1})

            assert len(topics) == 1

    @pytest.mark.asyncio
    async def test_collect_filters_by_min_score(
        self, web_scraper: ConcreteWebScraper, mock_html: str
    ):
        """Test that low-score items are filtered."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            # Collect with high min_score
            topics = await web_scraper.collect(params={"min_score": 60})

            # Only the first article (score 100) should pass
            assert len(topics) == 1
            assert topics[0].metrics["score"] == 100

    @pytest.mark.asyncio
    async def test_collect_handles_empty_base_url(self, source_id: uuid.UUID):
        """Test handling when base_url is not configured."""
        config = WebScraperConfig(base_url=None, name="Test Scraper")
        scraper = ConcreteWebScraper(config=config, source_id=source_id)

        topics = await scraper.collect()

        assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_collect_handles_fetch_error(self, web_scraper: ConcreteWebScraper):
        """Test graceful handling of HTTP errors."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.get.side_effect = httpx.ConnectError("Connection failed")

            topics = await web_scraper.collect()

            assert len(topics) == 0


class TestWebScraperHealthCheck:
    """Tests for WebScraperSource.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, web_scraper: ConcreteWebScraper):
        """Test health check returns True when site is accessible."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_instance.get.return_value = mock_response

            result = await web_scraper.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, web_scraper: ConcreteWebScraper):
        """Test health check returns False when site is down."""
        with patch("app.services.collector.sources.web_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.get.side_effect = httpx.ConnectError("Connection failed")

            result = await web_scraper.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_no_base_url(self, source_id: uuid.UUID):
        """Test health check returns False when no base_url configured."""
        config = WebScraperConfig(base_url=None, name="Test Scraper")
        scraper = ConcreteWebScraper(config=config, source_id=source_id)

        result = await scraper.health_check()

        assert result is False


class TestWebScraperRateLimiting:
    """Tests for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_applies_delay(self, source_id: uuid.UUID):
        """Test that rate limiting adds delay between requests."""
        config = WebScraperConfig(
            base_url="https://example.com",
            name="Test Scraper",
            rate_limit_delay=0.1,
        )
        scraper = ConcreteWebScraper(config=config, source_id=source_id)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await scraper._rate_limit()
            mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_no_delay_when_zero(self, source_id: uuid.UUID):
        """Test no delay when rate_limit_delay is 0."""
        config = WebScraperConfig(
            base_url="https://example.com",
            name="Test Scraper",
            rate_limit_delay=0,
        )
        scraper = ConcreteWebScraper(config=config, source_id=source_id)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await scraper._rate_limit()
            mock_sleep.assert_not_called()


class TestWebScraperHeaders:
    """Tests for HTTP header generation."""

    def test_get_headers_returns_user_agent(self, web_scraper: ConcreteWebScraper):
        """Test that headers include User-Agent."""
        headers = web_scraper._get_headers()

        assert "User-Agent" in headers
        assert "Mozilla" in headers["User-Agent"]
        assert "Accept" in headers
        assert "Accept-Language" in headers

    def test_custom_user_agent(self, source_id: uuid.UUID):
        """Test custom User-Agent from config."""
        config = WebScraperConfig(
            base_url="https://example.com",
            name="Test Scraper",
            user_agent="CustomBot/1.0",
        )
        scraper = ConcreteWebScraper(config=config, source_id=source_id)

        headers = scraper._get_headers()

        assert headers["User-Agent"] == "CustomBot/1.0"
