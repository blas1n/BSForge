"""Unit tests for Reddit source collector.

Tests use mocked HTTP responses to avoid external API calls.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config.sources import RedditConfig
from app.services.collector.sources.reddit import RedditSource


@pytest.fixture
def source_id() -> uuid.UUID:
    """Create a test source UUID."""
    return uuid.uuid4()


@pytest.fixture
def reddit_source(source_id: uuid.UUID) -> RedditSource:
    """Create Reddit source with test config."""
    config = RedditConfig(
        subreddits=["programming", "technology"],
        limit=10,
        min_score=100,
        sort="hot",
        time="day",
        request_timeout=15.0,
    )
    return RedditSource(config=config, source_id=source_id)


@pytest.fixture
def mock_post() -> dict:
    """Create a mock Reddit post."""
    return {
        "kind": "t3",
        "data": {
            "id": "abc123",
            "title": "Test Post Title",
            "url": "https://example.com/article",
            "permalink": "/r/programming/comments/abc123/test_post/",
            "score": 500,
            "upvote_ratio": 0.95,
            "num_comments": 150,
            "total_awards_received": 3,
            "author": "testuser",
            "created_utc": 1702400000,
            "selftext": "",
            "is_self": False,
            "stickied": False,
            "link_flair_text": "Discussion",
            "domain": "example.com",
        },
    }


@pytest.fixture
def mock_self_post() -> dict:
    """Create a mock Reddit self post (text post)."""
    return {
        "kind": "t3",
        "data": {
            "id": "xyz789",
            "title": "Ask: What is your favorite framework?",
            "url": "/r/programming/comments/xyz789/ask_favorite_framework/",
            "permalink": "/r/programming/comments/xyz789/ask_favorite_framework/",
            "score": 300,
            "upvote_ratio": 0.90,
            "num_comments": 200,
            "total_awards_received": 1,
            "author": "curious_dev",
            "created_utc": 1702400000,
            "selftext": "I'm looking for recommendations...",
            "is_self": True,
            "stickied": False,
            "link_flair_text": None,
            "domain": "self.programming",
        },
    }


class TestRedditCollect:
    """Tests for Reddit.collect() method."""

    @pytest.mark.asyncio
    async def test_collect_success(self, reddit_source: RedditSource, mock_post: dict):
        """Test successful collection from Reddit."""
        mock_response_data = {
            "data": {
                "children": [mock_post],
            }
        }

        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.json = lambda: mock_response_data
            mock_response.raise_for_status = lambda: None

            # Return same response for each subreddit
            mock_instance.get.return_value = mock_response

            topics = await reddit_source.collect()

            # Should have posts from both subreddits
            assert len(topics) == 2  # One from each subreddit
            assert topics[0].title == "Test Post Title"

    @pytest.mark.asyncio
    async def test_collect_no_subreddits_returns_empty(self, source_id: uuid.UUID):
        """Test that empty subreddit list returns empty results."""
        config = RedditConfig(subreddits=[])
        source = RedditSource(config=config, source_id=source_id)
        topics = await source.collect()
        assert topics == []

    @pytest.mark.asyncio
    async def test_collect_filters_low_score(self, reddit_source: RedditSource, mock_post: dict):
        """Test that low-score posts are filtered out."""
        mock_post["data"]["score"] = 50  # Below min_score of 100

        mock_response_data = {
            "data": {
                "children": [mock_post],
            }
        }

        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.json = lambda: mock_response_data
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            topics = await reddit_source.collect()

            assert len(topics) == 0  # Filtered out

    @pytest.mark.asyncio
    async def test_collect_with_params_override(self, reddit_source: RedditSource, mock_post: dict):
        """Test collection with parameter overrides."""
        mock_response_data = {
            "data": {
                "children": [mock_post],
            }
        }

        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.json = lambda: mock_response_data
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            # Override subreddits
            topics = await reddit_source.collect(
                params={"subreddits": ["python"], "min_score": 200}
            )

            assert len(topics) == 1  # Only one subreddit

    @pytest.mark.asyncio
    async def test_collect_skips_stickied_posts(self, reddit_source: RedditSource, mock_post: dict):
        """Test that stickied posts are skipped."""
        mock_post["data"]["stickied"] = True

        mock_response_data = {
            "data": {
                "children": [mock_post],
            }
        }

        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.json = lambda: mock_response_data
            mock_response.raise_for_status = lambda: None
            mock_instance.get.return_value = mock_response

            topics = await reddit_source.collect()

            assert len(topics) == 0  # Stickied posts filtered


class TestRedditHealthCheck:
    """Tests for Reddit.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, reddit_source: RedditSource):
        """Test health check returns True when API is accessible."""
        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_instance.get.return_value = mock_response

            result = await reddit_source.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, reddit_source: RedditSource):
        """Test health check returns False when API is down."""
        with patch("app.services.collector.sources.reddit.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.get.side_effect = httpx.ConnectError("Connection failed")

            result = await reddit_source.health_check()

            assert result is False


class TestRedditConversion:
    """Tests for post to RawTopic conversion."""

    def test_to_raw_topic_extracts_metadata(self, reddit_source: RedditSource, mock_post: dict):
        """Test that metadata is correctly extracted."""
        topic = reddit_source._to_raw_topic(mock_post["data"], "programming")

        assert topic is not None
        assert topic.metadata["reddit_id"] == "abc123"
        assert topic.metadata["subreddit"] == "programming"
        assert topic.metadata["author"] == "testuser"
        assert topic.metadata["flair"] == "Discussion"

    def test_to_raw_topic_extracts_metrics(self, reddit_source: RedditSource, mock_post: dict):
        """Test that metrics are correctly extracted."""
        topic = reddit_source._to_raw_topic(mock_post["data"], "programming")

        assert topic is not None
        assert topic.metrics["score"] == 500
        assert topic.metrics["upvote_ratio"] == 0.95
        assert topic.metrics["comments"] == 150
        assert topic.metrics["awards"] == 3

    def test_to_raw_topic_self_post_uses_reddit_url(
        self, reddit_source: RedditSource, mock_self_post: dict
    ):
        """Test that self posts use Reddit URL."""
        topic = reddit_source._to_raw_topic(mock_self_post["data"], "programming")

        assert topic is not None
        assert "reddit.com" in str(topic.source_url)
        assert topic.content == "I'm looking for recommendations..."

    def test_to_raw_topic_parses_timestamp(self, reddit_source: RedditSource, mock_post: dict):
        """Test that Unix timestamp is converted to datetime."""
        topic = reddit_source._to_raw_topic(mock_post["data"], "programming")

        assert topic is not None
        assert topic.published_at is not None
        assert isinstance(topic.published_at, datetime)
        assert topic.published_at.tzinfo == UTC

    def test_to_raw_topic_handles_deleted_content(
        self, reddit_source: RedditSource, mock_self_post: dict
    ):
        """Test handling of deleted post content."""
        mock_self_post["data"]["selftext"] = "[deleted]"

        topic = reddit_source._to_raw_topic(mock_self_post["data"], "programming")

        assert topic is not None
        assert topic.content is None  # Deleted content is set to None
