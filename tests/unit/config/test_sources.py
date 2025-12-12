"""Unit tests for source configuration models."""

import pytest
from pydantic import ValidationError

from app.config.sources import (
    HackerNewsConfig,
    RedditConfig,
    RSSConfig,
)


class TestHackerNewsConfig:
    """Tests for HackerNews configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HackerNewsConfig()
        assert config.limit == 30
        assert config.min_score == 50
        assert config.request_timeout == 10.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = HackerNewsConfig(limit=50, min_score=100, request_timeout=20.0)
        assert config.limit == 50
        assert config.min_score == 100
        assert config.request_timeout == 20.0

    def test_limit_validation(self):
        """Test limit must be between 1 and 100."""
        with pytest.raises(ValidationError):
            HackerNewsConfig(limit=0)
        with pytest.raises(ValidationError):
            HackerNewsConfig(limit=101)

    def test_min_score_validation(self):
        """Test min_score must be non-negative."""
        config = HackerNewsConfig(min_score=0)
        assert config.min_score == 0
        # Negative should fail
        with pytest.raises(ValidationError):
            HackerNewsConfig(min_score=-1)


class TestRedditConfig:
    """Tests for Reddit configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RedditConfig()
        assert config.subreddits == []
        assert config.limit == 25
        assert config.min_score == 100
        assert config.sort == "hot"
        assert config.time == "day"
        assert config.request_timeout == 10.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RedditConfig(
            subreddits=["python", "programming"],
            limit=50,
            min_score=200,
            sort="top",
            time="week",
        )
        assert config.subreddits == ["python", "programming"]
        assert config.limit == 50
        assert config.min_score == 200
        assert config.sort == "top"
        assert config.time == "week"

    def test_sort_validation(self):
        """Test sort must be valid option."""
        valid_sorts = ["hot", "new", "top", "rising"]
        for sort in valid_sorts:
            config = RedditConfig(sort=sort)
            assert config.sort == sort

        with pytest.raises(ValidationError):
            RedditConfig(sort="invalid")

    def test_time_validation(self):
        """Test time filter must be valid option."""
        valid_times = ["hour", "day", "week", "month", "year", "all"]
        for time in valid_times:
            config = RedditConfig(time=time)
            assert config.time == time

        with pytest.raises(ValidationError):
            RedditConfig(time="invalid")


class TestRSSConfig:
    """Tests for RSS configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RSSConfig()
        assert config.feed_url is None
        assert config.name == "RSS Feed"
        assert config.limit == 20
        assert config.request_timeout == 15.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RSSConfig(
            feed_url="https://example.com/feed.xml",
            name="My Feed",
            limit=50,
        )
        assert config.feed_url == "https://example.com/feed.xml"
        assert config.name == "My Feed"
        assert config.limit == 50


class TestSourceConfigDI:
    """Tests for source config DI integration."""

    def test_configs_are_independent(self):
        """Test that each config type creates independent instances."""
        hn1 = HackerNewsConfig()
        hn2 = HackerNewsConfig()
        assert hn1 is not hn2
        assert hn1.limit == hn2.limit

        reddit1 = RedditConfig()
        reddit2 = RedditConfig()
        assert reddit1 is not reddit2
        assert reddit1.subreddits == reddit2.subreddits

        rss1 = RSSConfig()
        rss2 = RSSConfig()
        assert rss1 is not rss2
        assert rss1.name == rss2.name
