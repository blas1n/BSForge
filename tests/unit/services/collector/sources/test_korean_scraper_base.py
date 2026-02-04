"""Unit tests for Korean web scraper base module."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.collector.sources.korean_scraper_base import KoreanWebScraperBase


class ConcreteKoreanScraper(KoreanWebScraperBase):
    """Concrete implementation for testing."""

    _config: MagicMock

    def __init__(self):
        self._config = MagicMock()
        self._config.base_url = "https://example.com"
        self._config.limit = 20
        self._config.min_score = 10
        self._http = MagicMock()
        self.source_id = "test-source"

    @property
    def source_name_kr(self) -> str:
        return "테스트사이트"

    @classmethod
    def build_config(cls, overrides):
        return MagicMock()

    def _get_list_urls(self, base_url, params):
        return [f"{base_url}/board"]

    def _parse_list_page(self, soup, url):
        return []


class TestKoreanWebScraperBase:
    """Tests for KoreanWebScraperBase class."""

    @pytest.fixture
    def scraper(self):
        """Create test scraper instance."""
        return ConcreteKoreanScraper()

    # ============================================
    # Number Parsing Tests
    # ============================================

    def test_parse_number_regular(self, scraper):
        """Test parsing regular numbers."""
        assert scraper._parse_number("1234") == 1234
        assert scraper._parse_number("0") == 0

    def test_parse_number_with_commas(self, scraper):
        """Test parsing numbers with comma separators."""
        assert scraper._parse_number("1,234") == 1234
        assert scraper._parse_number("1,234,567") == 1234567

    def test_parse_number_k_format(self, scraper):
        """Test parsing K suffix format."""
        assert scraper._parse_number("1.2k") == 1200
        assert scraper._parse_number("1.5K") == 1500
        assert scraper._parse_number("10k") == 10000

    def test_parse_number_man_format(self, scraper):
        """Test parsing 만 (10000) suffix format."""
        assert scraper._parse_number("1.2만") == 12000
        assert scraper._parse_number("3만") == 30000

    def test_parse_number_empty(self, scraper):
        """Test parsing empty/invalid input."""
        assert scraper._parse_number("") == 0
        assert scraper._parse_number("   ") == 0
        assert scraper._parse_number("abc") == 0

    def test_parse_number_invalid_k(self, scraper):
        """Test parsing invalid K format."""
        assert scraper._parse_number("abck") == 0

    def test_parse_number_invalid_man(self, scraper):
        """Test parsing invalid 만 format."""
        assert scraper._parse_number("abc만") == 0

    # ============================================
    # Korean Relative Date Tests
    # ============================================

    def test_parse_korean_relative_now(self, scraper):
        """Test parsing '방금' (just now)."""
        result = scraper._parse_korean_relative_date("방금")
        assert result is not None
        assert (datetime.now(UTC) - result).total_seconds() < 5

        result = scraper._parse_korean_relative_date("방금 전")
        assert result is not None

    def test_parse_korean_relative_seconds(self, scraper):
        """Test parsing seconds ago."""
        result = scraper._parse_korean_relative_date("30초 전")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(seconds=30)
        assert abs((result - expected).total_seconds()) < 5

        result = scraper._parse_korean_relative_date("10초전")
        assert result is not None

    def test_parse_korean_relative_minutes(self, scraper):
        """Test parsing minutes ago."""
        result = scraper._parse_korean_relative_date("5분 전")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(minutes=5)
        assert abs((result - expected).total_seconds()) < 5

        result = scraper._parse_korean_relative_date("15분전")
        assert result is not None

    def test_parse_korean_relative_hours(self, scraper):
        """Test parsing hours ago."""
        result = scraper._parse_korean_relative_date("3시간 전")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(hours=3)
        assert abs((result - expected).total_seconds()) < 60

        result = scraper._parse_korean_relative_date("2시간전")
        assert result is not None

    def test_parse_korean_relative_days(self, scraper):
        """Test parsing days ago."""
        result = scraper._parse_korean_relative_date("2일 전")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(days=2)
        assert abs((result - expected).total_seconds()) < 60

        result = scraper._parse_korean_relative_date("1일전")
        assert result is not None

    def test_parse_korean_relative_yesterday(self, scraper):
        """Test parsing '어제' (yesterday)."""
        result = scraper._parse_korean_relative_date("어제")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 60

    def test_parse_korean_relative_day_before_yesterday(self, scraper):
        """Test parsing '그저께'/'그제' (day before yesterday)."""
        result = scraper._parse_korean_relative_date("그저께")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(days=2)
        assert abs((result - expected).total_seconds()) < 60

        result = scraper._parse_korean_relative_date("그제")
        assert result is not None

    def test_parse_korean_relative_empty(self, scraper):
        """Test parsing empty input."""
        assert scraper._parse_korean_relative_date("") is None
        assert scraper._parse_korean_relative_date(None) is None

    def test_parse_korean_relative_no_number(self, scraper):
        """Test parsing relative date without number."""
        # Should return now if no number found
        result = scraper._parse_korean_relative_date("분 전")
        assert result is not None

    # ============================================
    # General Date Parsing Tests
    # ============================================

    def test_parse_date_iso_format(self, scraper):
        """Test parsing ISO date format."""
        result = scraper._parse_date("2025-01-15 14:30:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_korean_format(self, scraper):
        """Test parsing Korean date format."""
        result = scraper._parse_date("2025.01.15")
        assert result is not None
        assert result.year == 2025

        result = scraper._parse_date("2025.01.15 14:30")
        assert result is not None

    def test_parse_date_short_format(self, scraper):
        """Test parsing short date format (MM-DD)."""
        result = scraper._parse_date("01-15")
        assert result is not None
        assert result.month == 1
        assert result.day == 15
        assert result.year == datetime.now(UTC).year

    def test_parse_date_korean_relative(self, scraper):
        """Test parsing Korean relative date via _parse_date."""
        result = scraper._parse_date("3시간 전")
        assert result is not None

    def test_parse_date_empty(self, scraper):
        """Test parsing empty date."""
        assert scraper._parse_date("") is None
        assert scraper._parse_date(None) is None

    def test_parse_date_invalid(self, scraper):
        """Test parsing invalid date."""
        result = scraper._parse_date("not a date")
        assert result is None

    # ============================================
    # Board Extraction Tests
    # ============================================

    def test_extract_board_default(self, scraper):
        """Test default board extraction returns None."""
        result = scraper._extract_board("https://example.com/board")
        assert result is None

    # ============================================
    # RawTopic Conversion Tests
    # ============================================

    def test_to_raw_topic_minimal(self, scraper):
        """Test converting minimal item to RawTopic."""
        item = {
            "title": "Test Title",
            "url": "https://example.com/post/1",
        }

        result = scraper._to_raw_topic(item)

        assert result is not None
        assert result.title == "Test Title"
        assert str(result.source_url) == "https://example.com/post/1"
        assert result.source_id == "test-source"

    def test_to_raw_topic_full(self, scraper):
        """Test converting full item to RawTopic."""
        item = {
            "title": "Test Title",
            "url": "https://example.com/post/1",
            "score": 100,
            "views": 500,
            "comments": 20,
            "likes": 50,
            "author": "testuser",
            "board": "humor",
            "published_at": datetime.now(UTC),
        }

        result = scraper._to_raw_topic(item)

        assert result is not None
        assert result.title == "Test Title"
        assert result.metrics["score"] == 100
        assert result.metrics["views"] == 500
        assert result.metrics["comments"] == 20
        assert result.metrics["likes"] == 50
        assert result.metadata["author"] == "testuser"
        assert result.metadata["board"] == "humor"
        assert result.metadata["source_name"] == "테스트사이트"
        assert "작성자: testuser" in result.content
        assert "게시판: humor" in result.content

    def test_to_raw_topic_missing_title(self, scraper):
        """Test conversion fails without title."""
        item = {
            "url": "https://example.com/post/1",
        }

        result = scraper._to_raw_topic(item)
        assert result is None

    def test_to_raw_topic_missing_url(self, scraper):
        """Test conversion fails without URL."""
        item = {
            "title": "Test Title",
        }

        result = scraper._to_raw_topic(item)
        assert result is None

    def test_to_raw_topic_empty_metrics(self, scraper):
        """Test conversion with no metrics."""
        item = {
            "title": "Test Title",
            "url": "https://example.com/post/1",
        }

        result = scraper._to_raw_topic(item)

        assert result is not None
        assert result.metrics == {}

    def test_source_name_kr_property(self, scraper):
        """Test source_name_kr property."""
        assert scraper.source_name_kr == "테스트사이트"
