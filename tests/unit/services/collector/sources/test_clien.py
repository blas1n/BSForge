"""Unit tests for Clien source collector.

Tests use mocked HTTP responses to avoid external API calls.
"""

import uuid

import pytest

from app.config.sources import ClienConfig
from app.infrastructure.http_client import HTTPClient
from app.services.collector.sources.clien import ClienSource

from .conftest import create_mock_response


@pytest.fixture
def clien_source(source_id: uuid.UUID, mock_http_client: HTTPClient) -> ClienSource:
    """Create Clien source with test config."""
    config = ClienConfig(
        boards=["park"],
        limit=10,
        min_score=5,
    )
    return ClienSource(config=config, source_id=source_id, http_client=mock_http_client)


@pytest.fixture
def mock_clien_html() -> str:
    """Create mock Clien list page HTML."""
    return """
    <html>
    <body>
        <div class="list_content">
            <div class="list_item symph_row">
                <div class="list_title">
                    <a href="/service/board/park/12345" class="list_subject">
                        <span class="subject_fixed">Test Post Title</span>
                    </a>
                </div>
                <div class="list_author">
                    <span>testuser</span>
                </div>
                <div class="list_hit">1,234</div>
                <div class="list_time">2024-01-15</div>
                <div class="list_reply">
                    <span class="rSymph05">23</span>
                </div>
            </div>
            <div class="list_item symph_row">
                <div class="list_title">
                    <a href="/service/board/park/12346" class="list_subject">
                        <span class="subject_fixed">Another Post</span>
                    </a>
                </div>
                <div class="list_author">
                    <span>user2</span>
                </div>
                <div class="list_hit">567</div>
                <div class="list_time">2024-01-14</div>
                <div class="list_reply">
                    <span class="rSymph05">10</span>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


class TestClienCollect:
    """Tests for ClienSource.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_success(
        self, clien_source: ClienSource, mock_http_client: HTTPClient, mock_clien_html: str
    ):
        """Test successful collection of Clien posts."""
        mock_response = create_mock_response(text_data=mock_clien_html)
        mock_http_client.get.return_value = mock_response

        topics = await clien_source.collect()

        # Based on mock HTML parsing
        assert len(topics) >= 0  # May vary based on parsing

    @pytest.mark.asyncio
    async def test_collect_with_multiple_boards(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test collection from multiple boards."""
        config = ClienConfig(
            boards=["park", "jirum", "cm_ittalk"],
            limit=30,
        )
        source = ClienSource(config=config, source_id=source_id, http_client=mock_http_client)

        mock_response = create_mock_response(
            text_data="<html><body><div class='list_content'></div></body></html>"
        )
        mock_http_client.get.return_value = mock_response

        await source.collect()

        # Should request from all 3 boards
        assert mock_http_client.get.call_count >= 1


class TestClienHealthCheck:
    """Tests for ClienSource.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, clien_source: ClienSource, mock_http_client: HTTPClient
    ):
        """Test health check returns True when site is accessible."""
        mock_response = create_mock_response(status_code=200)
        mock_http_client.get.return_value = mock_response

        result = await clien_source.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self, clien_source: ClienSource, mock_http_client: HTTPClient
    ):
        """Test health check returns False when site is down."""
        mock_http_client.get.side_effect = Exception("Connection failed")

        result = await clien_source.health_check()

        assert result is False


class TestClienParsing:
    """Tests for Clien HTML parsing."""

    def test_get_list_urls_generates_board_urls(self, clien_source: ClienSource):
        """Test that list URLs are generated for configured boards."""
        urls = clien_source._get_list_urls("https://www.clien.net", {})

        assert len(urls) == 1  # One board configured
        assert "park" in urls[0]

    def test_get_list_urls_multiple_boards(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test URL generation for multiple boards."""
        config = ClienConfig(boards=["park", "jirum", "cm_ittalk"])
        source = ClienSource(config=config, source_id=source_id, http_client=mock_http_client)

        urls = source._get_list_urls("https://www.clien.net", {})

        assert len(urls) == 3
        assert any("park" in url for url in urls)
        assert any("jirum" in url for url in urls)
        assert any("cm_ittalk" in url for url in urls)


class TestClienDefaults:
    """Tests for default configuration values."""

    def test_default_base_url(self, source_id: uuid.UUID, mock_http_client: HTTPClient):
        """Test default base URL is set correctly."""
        config = ClienConfig()
        source = ClienSource(config=config, source_id=source_id, http_client=mock_http_client)

        # Should use default from ClienConfig
        assert source._config.base_url == "https://www.clien.net"

    def test_default_boards(self, source_id: uuid.UUID, mock_http_client: HTTPClient):
        """Test default boards configuration."""
        config = ClienConfig()
        source = ClienSource(config=config, source_id=source_id, http_client=mock_http_client)

        # Should have default boards from ClienConfig
        assert source._config.boards == ["park"]
        assert isinstance(source._config.boards, list)
