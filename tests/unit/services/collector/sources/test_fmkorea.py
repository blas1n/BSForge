"""Unit tests for FM Korea source collector."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.services.collector.sources.fmkorea import FmkoreaSource


class TestFmkoreaSource:
    """Tests for FmkoreaSource class."""

    @pytest.fixture
    def source(self):
        """Create FmkoreaSource instance with mocked dependencies."""
        with patch.object(FmkoreaSource, "__init__", lambda x: None):
            source = FmkoreaSource()
            source._config = MagicMock()
            source._config.base_url = "https://www.fmkorea.com"
            source._config.boards = ["best"]
            source._config.limit = 20
            source._config.min_score = 10
            source._http = MagicMock()
            source.source_id = "fmkorea"
            return source

    def test_build_config_defaults(self):
        """Test build_config with default values."""
        config = FmkoreaSource.build_config({})

        assert config.boards == ["best"]
        assert config.min_score == 10
        assert config.limit == 20

    def test_build_config_with_overrides(self):
        """Test build_config with custom values."""
        overrides = {
            "params": {"boards": ["humor", "starfree"]},
            "filters": {"min_score": 50},
            "limit": 50,
        }

        config = FmkoreaSource.build_config(overrides)

        assert config.boards == ["humor", "starfree"]
        assert config.min_score == 50
        assert config.limit == 50

    def test_source_name_kr(self, source):
        """Test Korean source name property."""
        assert source.source_name_kr == "FM코리아"

    def test_is_global_false(self):
        """Test is_global is False (scoped source)."""
        assert FmkoreaSource.is_global is False

    def test_get_list_urls(self, source):
        """Test URL generation for boards."""
        urls = source._get_list_urls("https://www.fmkorea.com", {"boards": ["best", "humor"]})

        assert len(urls) == 2
        assert "https://www.fmkorea.com/best" in urls
        assert "https://www.fmkorea.com/humor" in urls

    def test_get_list_urls_from_config(self, source):
        """Test URL generation using config boards."""
        source._config.boards = ["starfree"]
        urls = source._get_list_urls("https://www.fmkorea.com", {})

        assert len(urls) == 1
        assert "https://www.fmkorea.com/starfree" in urls

    def test_parse_list_page_empty(self, source):
        """Test parsing empty page."""
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://www.fmkorea.com/best")

        assert items == []

    def test_parse_best_post_item(self, source):
        """Test parsing best page post item."""
        html = """
        <li class="li">
            <h3 class="title">
                <a href="/12345">
                    <span class="ellipsis-target">Test Post Title</span>
                </a>
            </h3>
            <a class="pc_voted_count"><span class="count">150</span></a>
            <span class="comment_count">25</span>
            <span class="author">testuser</span>
            <span class="regdate">2025.01.15</span>
            <span class="category"><a>유머</a></span>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("li.li")

        item = source._parse_best_post_item(post, "https://www.fmkorea.com/best")

        assert item is not None
        assert item["title"] == "Test Post Title"
        assert item["post_id"] == "12345"
        assert item["score"] == 150
        assert item["recommends"] == 150
        assert item["comments"] == 25
        assert item["author"] == "testuser"
        assert item["category"] == "유머"
        assert item["board"] == "best"

    def test_parse_best_post_item_no_title(self, source):
        """Test parsing post without title returns None."""
        html = """<li class="li"><div>No title here</div></li>"""
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("li.li")

        item = source._parse_best_post_item(post, "https://www.fmkorea.com/best")

        assert item is None

    def test_parse_best_post_item_no_href(self, source):
        """Test parsing post without href returns None."""
        html = """
        <li class="li">
            <h3 class="title"><a><span class="ellipsis-target">Title</span></a></h3>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("li.li")

        item = source._parse_best_post_item(post, "https://www.fmkorea.com/best")

        assert item is None

    def test_parse_table_post_item(self, source):
        """Test parsing table format post item."""
        html = """
        <tr class="table_body">
            <td class="title">
                <a href="/54321">Table Post Title</a>
                <a class="replyNum">30</a>
            </td>
            <td class="m_no_voted">200</td>
            <td class="m_no">5000</td>
            <td class="author"><a>tableuser</a></td>
            <td class="time">2025.01.15</td>
            <td class="cate"><a>뉴스</a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_table_post_item(post, "https://www.fmkorea.com/humor")

        assert item is not None
        assert item["title"] == "Table Post Title"
        assert item["post_id"] == "54321"
        assert item["score"] == 200
        assert item["views"] == 5000
        assert item["comments"] == 30
        assert item["author"] == "tableuser"
        assert item["category"] == "뉴스"

    def test_parse_table_post_item_no_title_cell(self, source):
        """Test parsing table post without title cell returns None."""
        html = """<tr class="table_body"><td>Other content</td></tr>"""
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("tr.table_body")

        item = source._parse_table_post_item(post, "https://www.fmkorea.com/humor")

        assert item is None

    def test_parse_date_time_only(self, source):
        """Test parsing time-only format."""
        result = source._parse_date("14:30")

        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_date_short_year(self, source):
        """Test parsing short year date format."""
        result = source._parse_date("25.01.15")

        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_relative(self, source):
        """Test parsing Korean relative date."""
        result = source._parse_date("3시간 전")

        assert result is not None

    def test_parse_date_empty(self, source):
        """Test parsing empty date."""
        assert source._parse_date("") is None
        assert source._parse_date(None) is None

    def test_extract_board(self, source):
        """Test board extraction from URL."""
        result = source._extract_board("https://www.fmkorea.com/best")
        assert result == "best"

        result = source._extract_board("https://www.fmkorea.com/humor?page=1")
        assert result == "humor"

    def test_extract_board_unknown(self, source):
        """Test board extraction with unknown URL."""
        result = source._extract_board("https://example.com/other")
        assert result == "unknown"

    def test_to_raw_topic(self, source):
        """Test conversion to RawTopic."""
        item = {
            "title": "Test Title",
            "url": "https://www.fmkorea.com/12345",
            "score": 100,
            "recommends": 100,
            "comments": 20,
            "author": "testuser",
            "board": "best",
            "post_id": "12345",
            "category": "유머",
            "published_at": datetime.now(UTC),
        }

        result = source._to_raw_topic(item)

        assert result is not None
        assert result.title == "Test Title"
        assert result.metrics["recommends"] == 100
        assert result.metadata["post_id"] == "12345"
        assert result.metadata["category"] == "유머"

    def test_to_raw_topic_minimal(self, source):
        """Test conversion with minimal item."""
        item = {
            "title": "Minimal Title",
            "url": "https://www.fmkorea.com/12345",
        }

        result = source._to_raw_topic(item)

        assert result is not None
        assert result.title == "Minimal Title"

    def test_to_raw_topic_none_on_invalid(self, source):
        """Test conversion returns None on invalid item."""
        item = {"title": None, "url": None}

        result = source._to_raw_topic(item)

        assert result is None

    def test_parse_list_page_best_format(self, source):
        """Test parsing list page with best format."""
        html = """
        <html>
        <body>
            <li class="li">
                <h3 class="title">
                    <a href="/111"><span class="ellipsis-target">Post 1</span></a>
                </h3>
                <a class="pc_voted_count"><span class="count">50</span></a>
            </li>
            <li class="li">
                <h3 class="title">
                    <a href="/222"><span class="ellipsis-target">Post 2</span></a>
                </h3>
                <a class="pc_voted_count"><span class="count">100</span></a>
            </li>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://www.fmkorea.com/best")

        assert len(items) == 2
        assert items[0]["title"] == "Post 1"
        assert items[1]["title"] == "Post 2"

    def test_parse_list_page_table_format(self, source):
        """Test parsing list page with table format."""
        html = """
        <html>
        <body>
            <table class="bd_tb">
                <tbody>
                    <tr class="table_body">
                        <td class="title"><a href="/333">Table Post</a></td>
                        <td class="m_no_voted">75</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        items = source._parse_list_page(soup, "https://www.fmkorea.com/starfree")

        assert len(items) == 1
        assert items[0]["title"] == "Table Post"

    def test_title_cleanup_removes_comment_count(self, source):
        """Test title cleanup removes comment count suffix."""
        html = """
        <li class="li">
            <h3 class="title">
                <a href="/12345">
                    <span class="ellipsis-target">Test Title [25]</span>
                </a>
            </h3>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("li.li")

        item = source._parse_best_post_item(post, "https://www.fmkorea.com/best")

        assert item is not None
        assert item["title"] == "Test Title"
        assert "[25]" not in item["title"]
