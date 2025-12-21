"""Tests for source factory.

Tests the dynamic source instantiation via factory pattern.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.collector.sources.factory import collect_from_sources, create_source


class TestCreateSource:
    """Tests for create_source function."""

    def test_create_hackernews_source(self) -> None:
        """Test creating HackerNews source."""
        source = create_source("hackernews")
        assert source is not None
        assert source.__class__.__name__ == "HackerNewsSource"

    def test_create_hackernews_with_overrides(self) -> None:
        """Test creating HackerNews source with config overrides."""
        overrides = {
            "filters": {"min_score": 100},
            "limit": 20,
        }
        source = create_source("hackernews", overrides)
        assert source is not None
        assert source._config.min_score == 100
        assert source._config.limit == 20

    def test_create_reddit_source_requires_subreddits(self) -> None:
        """Test that Reddit source requires subreddits in overrides."""
        with pytest.raises(ValueError, match="subreddits"):
            create_source("reddit")

    def test_create_reddit_with_overrides(self) -> None:
        """Test creating Reddit source with custom subreddits."""
        overrides = {
            "params": {"subreddits": ["MachineLearning", "Python"]},
            "filters": {"min_score": 50},
            "limit": 15,
        }
        source = create_source("reddit", overrides)
        assert source is not None
        assert source._config.subreddits == ["MachineLearning", "Python"]
        assert source._config.min_score == 50
        assert source._config.limit == 15

    def test_create_youtube_trending_source(self) -> None:
        """Test creating YouTube Trending source."""
        source = create_source("youtube_trending")
        assert source is not None
        assert source.__class__.__name__ == "YouTubeTrendingSource"

    def test_create_google_trends_source(self) -> None:
        """Test creating Google Trends source."""
        source = create_source("google_trends")
        assert source is not None
        assert source.__class__.__name__ == "GoogleTrendsSource"

    def test_create_dcinside_source(self) -> None:
        """Test creating DCInside source."""
        source = create_source("dcinside")
        assert source is not None
        assert source.__class__.__name__ == "DCInsideSource"

    def test_create_dcinside_with_overrides(self) -> None:
        """Test creating DCInside source with custom galleries."""
        overrides = {
            "params": {"galleries": ["programming", "tech"], "gallery_type": "minor"},
            "filters": {"min_score": 100},
            "limit": 20,
        }
        source = create_source("dcinside", overrides)
        assert source is not None
        assert source._config.galleries == ["programming", "tech"]
        assert source._config.gallery_type == "minor"
        assert source._config.min_score == 100

    def test_create_clien_source(self) -> None:
        """Test creating Clien source."""
        source = create_source("clien")
        assert source is not None
        assert source.__class__.__name__ == "ClienSource"

    def test_create_clien_with_overrides(self) -> None:
        """Test creating Clien source with custom boards."""
        overrides = {
            "params": {"boards": ["park", "jirum"]},
            "filters": {"min_score": 50},
            "limit": 25,
        }
        source = create_source("clien", overrides)
        assert source is not None
        assert source._config.boards == ["park", "jirum"]
        assert source._config.min_score == 50

    def test_create_ruliweb_source(self) -> None:
        """Test creating Ruliweb source."""
        source = create_source("ruliweb")
        assert source is not None
        assert source.__class__.__name__ == "RuliwebSource"

    def test_create_fmkorea_source(self) -> None:
        """Test creating FMKorea source."""
        source = create_source("fmkorea")
        assert source is not None
        assert source.__class__.__name__ == "FmkoreaSource"

    def test_create_rss_source(self) -> None:
        """Test creating RSS source."""
        overrides = {
            "params": {"feed_url": "https://example.com/feed.xml", "name": "Example Feed"},
            "limit": 30,
        }
        source = create_source("rss", overrides)
        assert source is not None
        assert source.__class__.__name__ == "RSSSource"
        assert source._config.feed_url == "https://example.com/feed.xml"

    def test_create_rss_without_feed_url_raises(self) -> None:
        """Test that RSS source without feed_url raises ValueError."""
        with pytest.raises(ValueError, match="Failed to build config"):
            create_source("rss")

    def test_create_custom_rss_source(self) -> None:
        """Test creating custom RSS source with _rss suffix."""
        overrides = {
            "params": {"feed_url": "https://news.example.com/rss", "name": "News Feed"},
        }
        source = create_source("news_rss", overrides)
        assert source is not None
        assert source.__class__.__name__ == "RSSSource"

    def test_unknown_source_raises(self) -> None:
        """Test that unknown source type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown source type"):
            create_source("unknown_source")

    def test_custom_source_id(self) -> None:
        """Test creating source with custom source ID."""
        custom_id = uuid.uuid4()
        source = create_source("hackernews", source_id=custom_id)
        assert source is not None
        assert source.source_id == custom_id

    def test_generates_source_id_if_not_provided(self) -> None:
        """Test that source ID is generated if not provided."""
        source = create_source("hackernews")
        assert source is not None
        assert source.source_id is not None
        assert isinstance(source.source_id, uuid.UUID)


class TestCollectFromSources:
    """Tests for collect_from_sources function."""

    @pytest.mark.asyncio
    async def test_collect_from_single_source(self) -> None:
        """Test collecting from a single source."""
        mock_topics = [{"title": "Test Topic"}]

        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_source = AsyncMock()
            mock_source.collect.return_value = mock_topics
            mock_create.return_value = mock_source

            topics = await collect_from_sources(["hackernews"])

            assert len(topics) == 1
            mock_create.assert_called_once_with("hackernews", {}, http_client=None)

    @pytest.mark.asyncio
    async def test_collect_from_multiple_sources(self) -> None:
        """Test collecting from multiple sources."""
        mock_topics_hn = [{"title": "HN Topic"}]
        mock_topics_reddit = [{"title": "Reddit Topic"}]

        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_source_hn = AsyncMock()
            mock_source_hn.collect.return_value = mock_topics_hn

            mock_source_reddit = AsyncMock()
            mock_source_reddit.collect.return_value = mock_topics_reddit

            mock_create.side_effect = [mock_source_hn, mock_source_reddit]

            topics = await collect_from_sources(["hackernews", "reddit"])

            assert len(topics) == 2

    @pytest.mark.asyncio
    async def test_collect_applies_source_overrides(self) -> None:
        """Test that source overrides are applied."""
        overrides = {"hackernews": {"limit": 50}}

        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_source = AsyncMock()
            mock_source.collect.return_value = []
            mock_create.return_value = mock_source

            await collect_from_sources(["hackernews"], overrides)

            mock_create.assert_called_once_with("hackernews", {"limit": 50}, http_client=None)

    @pytest.mark.asyncio
    async def test_collect_skips_unknown_sources(self) -> None:
        """Test that unknown sources are skipped (error logged, continues)."""
        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_create.side_effect = ValueError("Unknown source type")

            topics = await collect_from_sources(["unknown_source"])

            assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_collect_handles_source_errors(self) -> None:
        """Test that errors from individual sources are handled gracefully."""
        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_source = AsyncMock()
            mock_source.collect.side_effect = Exception("Collection failed")
            mock_create.return_value = mock_source

            # Should not raise, just return empty list
            topics = await collect_from_sources(["hackernews"])

            assert len(topics) == 0

    @pytest.mark.asyncio
    async def test_collect_continues_on_error(self) -> None:
        """Test that collection continues even if one source fails."""
        mock_topics = [{"title": "Working Topic"}]

        with patch("app.services.collector.sources.factory.create_source") as mock_create:
            mock_source_ok = AsyncMock()
            mock_source_ok.collect.return_value = mock_topics

            # First call raises ValueError (unknown source), second returns working source
            mock_create.side_effect = [ValueError("Unknown source"), mock_source_ok]

            topics = await collect_from_sources(["failing_source", "working_source"])

            # Should have topics from the working source
            assert len(topics) == 1
