"""Unit tests for RSS source collector.

Tests use mocked HTTP responses to avoid external API calls.
"""

import uuid
from datetime import datetime

import pytest

from app.config.sources import RSSConfig
from app.infrastructure.http_client import HTTPClient
from app.services.collector.sources.rss import RSSSource

from .conftest import create_mock_response


@pytest.fixture
def rss_source(source_id: uuid.UUID, mock_http_client: HTTPClient) -> RSSSource:
    """Create RSS source with test config."""
    config = RSSConfig(
        feed_url="https://example.com/feed.xml",
        name="Example Feed",
        limit=10,
        request_timeout=15.0,
    )
    return RSSSource(config=config, source_id=source_id, http_client=mock_http_client)


@pytest.fixture
def mock_rss_feed() -> str:
    """Create a mock RSS 2.0 feed."""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Example Feed</title>
            <link>https://example.com</link>
            <description>An example RSS feed</description>
            <item>
                <title>Test Article Title</title>
                <link>https://example.com/article1</link>
                <description>This is the article summary.</description>
                <pubDate>Tue, 12 Dec 2023 10:00:00 GMT</pubDate>
                <author>author@example.com</author>
                <category>Technology</category>
                <category>Programming</category>
            </item>
            <item>
                <title>Second Article</title>
                <link>https://example.com/article2</link>
                <description>Another article summary.</description>
                <pubDate>Mon, 11 Dec 2023 15:30:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """


@pytest.fixture
def mock_atom_feed() -> str:
    """Create a mock Atom feed."""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Example Atom Feed</title>
        <link href="https://example.com"/>
        <entry>
            <title>Atom Article</title>
            <link href="https://example.com/atom-article"/>
            <content type="html">&lt;p&gt;Article content here.&lt;/p&gt;</content>
            <published>2023-12-12T10:00:00Z</published>
            <author>
                <name>John Doe</name>
            </author>
        </entry>
    </feed>
    """


class TestRSSCollect:
    """Tests for RSS.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_rss_success(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_rss_feed: str
    ):
        """Test successful collection from RSS feed."""
        mock_response = create_mock_response(text_data=mock_rss_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect()

        assert len(topics) == 2
        assert topics[0].title == "Test Article Title"
        assert topics[1].title == "Second Article"

    @pytest.mark.asyncio
    async def test_collect_atom_success(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_atom_feed: str
    ):
        """Test successful collection from Atom feed."""
        mock_response = create_mock_response(text_data=mock_atom_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect()

        assert len(topics) == 1
        assert topics[0].title == "Atom Article"

    @pytest.mark.asyncio
    async def test_collect_no_feed_url_returns_empty(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test that missing feed_url returns empty results."""
        config = RSSConfig()  # No feed_url
        source = RSSSource(config=config, source_id=source_id, http_client=mock_http_client)
        topics = await source.collect()
        assert topics == []

    @pytest.mark.asyncio
    async def test_collect_with_limit(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_rss_feed: str
    ):
        """Test collection respects limit parameter."""
        mock_response = create_mock_response(text_data=mock_rss_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect(params={"limit": 1})

        assert len(topics) == 1

    @pytest.mark.asyncio
    async def test_collect_http_error(self, rss_source: RSSSource, mock_http_client: HTTPClient):
        """Test that HTTP errors are raised."""
        mock_http_client.get.side_effect = Exception("HTTP Error")

        with pytest.raises(Exception, match="HTTP Error"):
            await rss_source.collect()


class TestRSSHealthCheck:
    """Tests for RSS.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, rss_source: RSSSource, mock_http_client: HTTPClient):
        """Test health check returns True when feed is accessible."""
        mock_response = create_mock_response(status_code=200)
        mock_http_client.get.return_value = mock_response

        result = await rss_source.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_no_url_returns_false(
        self, source_id: uuid.UUID, mock_http_client: HTTPClient
    ):
        """Test health check returns False when no URL configured."""
        config = RSSConfig()  # No feed_url
        source = RSSSource(config=config, source_id=source_id, http_client=mock_http_client)
        result = await source.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self, rss_source: RSSSource, mock_http_client: HTTPClient):
        """Test health check returns False when feed is down."""
        mock_http_client.get.side_effect = Exception("Connection failed")

        result = await rss_source.health_check()

        assert result is False


class TestRSSConversion:
    """Tests for entry to RawTopic conversion."""

    @pytest.mark.asyncio
    async def test_extracts_metadata(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_rss_feed: str
    ):
        """Test that metadata is correctly extracted."""
        mock_response = create_mock_response(text_data=mock_rss_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect()

        assert topics[0].metadata["source_name"] == "Example Feed"
        assert topics[0].metadata["author"] == "author@example.com"
        assert "Technology" in topics[0].metadata["tags"]

    @pytest.mark.asyncio
    async def test_parses_pubdate(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_rss_feed: str
    ):
        """Test that publication date is correctly parsed."""
        mock_response = create_mock_response(text_data=mock_rss_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect()

        assert topics[0].published_at is not None
        assert isinstance(topics[0].published_at, datetime)

    @pytest.mark.asyncio
    async def test_strips_html_from_content(
        self, rss_source: RSSSource, mock_http_client: HTTPClient, mock_atom_feed: str
    ):
        """Test that HTML is stripped from content."""
        mock_response = create_mock_response(text_data=mock_atom_feed)
        mock_http_client.get.return_value = mock_response

        topics = await rss_source.collect()

        assert topics[0].content is not None
        assert "<p>" not in topics[0].content
        assert "Article content here." in topics[0].content


class TestHTMLStripping:
    """Tests for HTML stripping utility."""

    def test_strip_html_removes_tags(self, rss_source: RSSSource):
        """Test HTML tag removal."""
        html = "<p>Hello <strong>world</strong>!</p>"
        result = rss_source._strip_html(html)
        assert result == "Hello world!"

    def test_strip_html_decodes_entities(self, rss_source: RSSSource):
        """Test HTML entity decoding."""
        html = "Hello &amp; goodbye &lt;3"
        result = rss_source._strip_html(html)
        assert result == "Hello & goodbye <3"

    def test_strip_html_normalizes_whitespace(self, rss_source: RSSSource):
        """Test whitespace normalization."""
        html = "Hello    world\n\ntest"
        result = rss_source._strip_html(html)
        assert result == "Hello world test"
