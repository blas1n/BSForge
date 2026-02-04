"""Unit tests for Ruliweb source collector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.services.collector.sources.ruliweb import RuliwebSource


class TestRuliwebSource:
    """Tests for RuliwebSource class."""

    @pytest.fixture
    def source(self):
        """Create RuliwebSource instance with mocked dependencies."""
        with patch.object(RuliwebSource, "__init__", lambda x: None):
            source = RuliwebSource()
            source._config = MagicMock()
            source._config.base_url = "https://bbs.ruliweb.com"
            source._config.boards = ["best/humor"]
            source._config.limit = 20
            source._config.min_score = 10
            source._http = MagicMock()
            source.source_id = "ruliweb"
            return source

    def test_build_config_defaults(self):
        """Test build_config with default values."""
        config = RuliwebSource.build_config({})

        assert config.boards == ["best/humor"]
        assert config.min_score == 10
        assert config.limit == 20

    def test_build_config_with_overrides(self):
        """Test build_config with custom values."""
        overrides = {
            "params": {"boards": ["best/all", "community/humor"]},
            "filters": {"min_score": 30},
            "limit": 40,
        }

        config = RuliwebSource.build_config(overrides)

        assert config.boards == ["best/all", "community/humor"]
        assert config.min_score == 30
        assert config.limit == 40

    def test_source_name_kr(self, source):
        """Test Korean source name property."""
        assert source.source_name_kr == "루리웹"

    def test_is_global_false(self):
        """Test is_global is False (scoped source)."""
        assert RuliwebSource.is_global is False

    def test_get_list_urls(self, source):
        """Test URL generation for boards."""
        urls = source._get_list_urls(
            "https://bbs.ruliweb.com", {"boards": ["best/humor", "best/all"]}
        )

        assert len(urls) == 2
        assert "https://bbs.ruliweb.com/best/humor" in urls
        assert "https://bbs.ruliweb.com/best/all" in urls

    def test_get_list_urls_from_config(self, source):
        """Test URL generation using config boards."""
        source._config.boards = ["community/rulilife"]
        urls = source._get_list_urls("https://bbs.ruliweb.com", {})

        assert len(urls) == 1
        assert "https://bbs.ruliweb.com/community/rulilife" in urls

    def test_parse_list_page_empty(self, source):
        """Test parsing empty page."""
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://bbs.ruliweb.com/best/humor")

        assert items == []

    def test_parse_post_item(self, source):
        """Test parsing table row post item."""
        html = """
        <tr class="table_body">
            <td class="id">12345</td>
            <td class="title">
                <a class="subject_link" href="/best/humor/12345">Test Post Title</a>
                <a class="num_reply">30</a>
            </td>
            <td class="recomd">150</td>
            <td class="hit">5000</td>
            <td class="writer">testuser</td>
            <td class="time">2025.01.15</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is not None
        assert item["title"] == "Test Post Title"
        assert item["post_id"] == "12345"
        assert item["score"] == 150
        assert item["recommends"] == 150
        assert item["views"] == 5000
        assert item["comments"] == 30
        assert item["author"] == "testuser"
        assert item["board"] == "best/humor"

    def test_parse_post_item_with_deco_link(self, source):
        """Test parsing post with deco class link."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a class="deco" href="/best/all/67890">Deco Link Post</a>
            </td>
            <td class="recomd">200</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/all")

        assert item is not None
        assert item["title"] == "Deco Link Post"

    def test_parse_post_item_no_title(self, source):
        """Test parsing post without title returns None."""
        html = """<tr class="table_body"><td>No link here</td></tr>"""
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is None

    def test_parse_post_item_empty_title(self, source):
        """Test parsing post with empty title returns None."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a class="subject_link" href="/post/1">   </a>
            </td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is None

    def test_parse_post_item_no_href(self, source):
        """Test parsing post without href returns None."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a class="subject_link">No Href</a>
            </td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is None

    def test_parse_post_item_cleans_badge_text(self, source):
        """Test that badge text is cleaned from title."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a class="subject_link" href="/post/1">베 Title After Badge</a>
            </td>
            <td class="recomd">50</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is not None
        assert item["title"] == "Title After Badge"

    def test_parse_post_item_author_from_link(self, source):
        """Test parsing author from link inside writer cell."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a class="subject_link" href="/post/1">Title</a>
            </td>
            <td class="writer"><a href="/user/123">linkeduser</a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_post_item(post, "https://bbs.ruliweb.com/best/humor")

        assert item is not None
        assert item["author"] == "linkeduser"

    def test_parse_date_time_only(self, source):
        """Test parsing time-only format."""
        result = source._parse_date("17:45")

        assert result is not None
        assert result.hour == 17
        assert result.minute == 45

    def test_parse_date_short_year(self, source):
        """Test parsing short year date format."""
        result = source._parse_date("25.01.15")

        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_with_time(self, source):
        """Test parsing date with time."""
        result = source._parse_date("25.01.15 14:30")

        assert result is not None
        assert result.year == 2025

    def test_parse_date_relative(self, source):
        """Test parsing Korean relative date."""
        result = source._parse_date("5분 전")

        assert result is not None

    def test_parse_date_empty(self, source):
        """Test parsing empty date."""
        assert source._parse_date("") is None
        assert source._parse_date(None) is None

    def test_extract_board_best(self, source):
        """Test board extraction for best boards."""
        result = source._extract_board("https://bbs.ruliweb.com/best/humor")
        assert result == "best/humor"

        result = source._extract_board("https://bbs.ruliweb.com/best/all?page=1")
        assert result == "best/all"

    def test_extract_board_community(self, source):
        """Test board extraction for community boards."""
        result = source._extract_board("https://bbs.ruliweb.com/community/humor")
        assert result == "community/humor"

    def test_extract_board_unknown(self, source):
        """Test board extraction with unknown URL."""
        result = source._extract_board("https://bbs.ruliweb.com/other")
        assert result == "unknown"

    def test_to_raw_topic(self, source):
        """Test conversion to RawTopic."""
        item = {
            "title": "Test Title",
            "url": "https://bbs.ruliweb.com/best/humor/12345",
            "score": 100,
            "recommends": 100,
            "views": 2000,
            "comments": 20,
            "author": "testuser",
            "board": "best/humor",
            "post_id": "12345",
            "published_at": datetime.now(UTC),
        }

        result = source._to_raw_topic(item)

        assert result is not None
        assert result.title == "Test Title"
        assert result.metrics["recommends"] == 100
        assert result.metadata["post_id"] == "12345"

    def test_to_raw_topic_minimal(self, source):
        """Test conversion with minimal item."""
        item = {
            "title": "Minimal Title",
            "url": "https://bbs.ruliweb.com/post/1",
        }

        result = source._to_raw_topic(item)

        assert result is not None
        assert result.title == "Minimal Title"

    def test_to_raw_topic_none_on_invalid(self, source):
        """Test conversion returns None on invalid item."""
        item = {"title": None, "url": None}

        result = source._to_raw_topic(item)

        assert result is None

    def test_parse_list_page(self, source):
        """Test parsing full list page."""
        html = """
        <html>
        <body>
            <tr class="table_body">
                <td class="title">
                    <a class="subject_link" href="/post/111">Post 1</a>
                </td>
                <td class="recomd">50</td>
            </tr>
            <tr class="table_body">
                <td class="title">
                    <a class="subject_link" href="/post/222">Post 2</a>
                </td>
                <td class="recomd">100</td>
            </tr>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://bbs.ruliweb.com/best/humor")

        assert len(items) == 2
        assert items[0]["title"] == "Post 1"
        assert items[1]["title"] == "Post 2"

    def test_parse_list_page_with_exception(self, source):
        """Test that parse_list_page handles individual item errors gracefully."""
        html = """
        <html>
        <body>
            <tr class="table_body">
                <td class="title">
                    <a class="subject_link" href="/post/111">Valid Post</a>
                </td>
            </tr>
            <tr class="table_body">
                <td class="invalid">No title here</td>
            </tr>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://bbs.ruliweb.com/best/humor")

        # Should get the valid post, skip the invalid one
        assert len(items) == 1
        assert items[0]["title"] == "Valid Post"
