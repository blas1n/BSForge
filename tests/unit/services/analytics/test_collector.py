"""Unit tests for YouTubeAnalyticsCollector service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.youtube_upload import AnalyticsConfig
from app.infrastructure.youtube_api import VideoAnalytics
from app.models.performance import Performance
from app.models.upload import Upload
from app.services.analytics.collector import (
    PerformanceSnapshot,
    YouTubeAnalyticsCollector,
)
from tests.conftest import make_mock_session_factory


class TestPerformanceSnapshot:
    """Tests for PerformanceSnapshot dataclass."""

    def test_default_values(self):
        """Test default instantiation with zeros."""
        snapshot = PerformanceSnapshot()

        assert snapshot.views == 0
        assert snapshot.likes == 0
        assert snapshot.dislikes == 0
        assert snapshot.comments == 0
        assert snapshot.shares == 0
        assert snapshot.watch_time_seconds == 0
        assert snapshot.avg_view_duration == 0.0
        assert snapshot.avg_view_percentage == 0.0
        assert snapshot.ctr == 0.0
        assert snapshot.subscribers_gained == 0
        assert snapshot.subscribers_lost == 0
        assert snapshot.traffic_sources is None
        assert snapshot.demographics is None
        assert snapshot.collected_at is not None

    def test_with_values(self):
        """Test instantiation with actual data."""
        snapshot = PerformanceSnapshot(
            views=1000,
            likes=50,
            comments=10,
            watch_time_seconds=3600,
            avg_view_duration=45.0,
            avg_view_percentage=75.0,
            traffic_sources={"SEARCH": 500, "BROWSE": 300},
        )

        assert snapshot.views == 1000
        assert snapshot.likes == 50
        assert snapshot.traffic_sources == {"SEARCH": 500, "BROWSE": 300}


class TestYouTubeAnalyticsCollector:
    """Tests for YouTubeAnalyticsCollector service."""

    @pytest.fixture
    def mock_youtube_api(self):
        """Create mock YouTube API client."""
        api = AsyncMock()
        api.get_video_analytics = AsyncMock(
            return_value=VideoAnalytics(
                video_id="yt_123",
                views=1000,
                likes=50,
                dislikes=5,
                comments=10,
                shares=20,
                watch_time_minutes=500,
                avg_view_duration_seconds=45.0,
                avg_view_percentage=75.0,
                subscribers_gained=15,
                subscribers_lost=2,
            )
        )
        api.get_traffic_sources = AsyncMock(
            return_value={"SEARCH": 400, "BROWSE": 300, "SUGGESTED": 200}
        )
        return api

    @pytest.fixture
    def mock_db_session_and_factory(self):
        """Create mock database session and factory."""
        return make_mock_session_factory()

    @pytest.fixture
    def mock_db_session_factory(self, mock_db_session_and_factory):
        """Get mock factory."""
        return mock_db_session_and_factory[0]

    @pytest.fixture
    def mock_db_session(self, mock_db_session_and_factory):
        """Get mock session."""
        return mock_db_session_and_factory[1]

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AnalyticsConfig(
            metrics_lookback_days=30,
            performance_percentile=90.0,
        )

    @pytest.fixture
    def collector(self, mock_youtube_api, mock_db_session_factory, config):
        """Create YouTubeAnalyticsCollector instance."""
        return YouTubeAnalyticsCollector(
            youtube_api=mock_youtube_api,
            db_session_factory=mock_db_session_factory,
            config=config,
        )

    # =========================================================================
    # collect_video_performance() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_collect_creates_performance_record(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test that collection creates a Performance record when none exists."""
        upload_id = uuid.uuid4()
        upload = MagicMock(spec=Upload)
        upload.id = upload_id
        upload.youtube_video_id = "yt_123"
        upload.performance = None

        mock_db_session.get = AsyncMock(return_value=upload)

        snapshot = await collector.collect_video_performance(upload_id)

        assert snapshot.views == 1000
        assert snapshot.likes == 50
        mock_db_session.add.assert_called_once()
        added_perf = mock_db_session.add.call_args[0][0]
        assert isinstance(added_perf, Performance)
        assert added_perf.upload_id == upload_id

    @pytest.mark.asyncio
    async def test_collect_updates_existing_performance(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test that collection updates an existing Performance record."""
        upload_id = uuid.uuid4()
        existing_perf = MagicMock(spec=Performance)
        existing_perf.daily_snapshots = [{"date": "2024-01-01", "views": 500}]

        upload = MagicMock(spec=Upload)
        upload.id = upload_id
        upload.youtube_video_id = "yt_123"
        upload.performance = existing_perf

        mock_db_session.get = AsyncMock(return_value=upload)

        snapshot = await collector.collect_video_performance(upload_id)

        assert snapshot.views == 1000
        # Should NOT add a new record
        mock_db_session.add.assert_not_called()
        # Should update existing
        assert existing_perf.views == 1000
        assert existing_perf.likes == 50

    @pytest.mark.asyncio
    async def test_collect_calculates_engagement_rate(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test engagement rate calculation: (likes + comments) / views."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = None

        mock_db_session.get = AsyncMock(return_value=upload)

        await collector.collect_video_performance(upload.id)

        added_perf = mock_db_session.add.call_args[0][0]
        # (50 likes + 10 comments) / 1000 views = 0.06
        assert added_perf.engagement_rate == pytest.approx(0.06)

    @pytest.mark.asyncio
    async def test_collect_converts_watch_time_to_seconds(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test that watch_time_minutes is converted to seconds."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = None

        mock_db_session.get = AsyncMock(return_value=upload)

        snapshot = await collector.collect_video_performance(upload.id)

        # 500 minutes * 60 = 30000 seconds
        assert snapshot.watch_time_seconds == 30000

    @pytest.mark.asyncio
    async def test_collect_fetches_traffic_sources(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test that traffic sources are fetched and stored."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = None

        mock_db_session.get = AsyncMock(return_value=upload)

        snapshot = await collector.collect_video_performance(upload.id)

        mock_youtube_api.get_traffic_sources.assert_called_once()
        assert snapshot.traffic_sources == {"SEARCH": 400, "BROWSE": 300, "SUGGESTED": 200}

    @pytest.mark.asyncio
    async def test_collect_appends_daily_snapshot(self, collector, mock_db_session):
        """Test that daily snapshot is appended to existing list."""
        existing_perf = MagicMock(spec=Performance)
        existing_perf.daily_snapshots = [{"date": "2024-01-01", "views": 500}]

        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = existing_perf

        mock_db_session.get = AsyncMock(return_value=upload)

        await collector.collect_video_performance(upload.id)

        assert len(existing_perf.daily_snapshots) == 2
        assert existing_perf.daily_snapshots[-1]["views"] == 1000

    @pytest.mark.asyncio
    async def test_collect_creates_first_daily_snapshot(self, collector, mock_db_session):
        """Test daily snapshot creation when none exist."""
        existing_perf = MagicMock(spec=Performance)
        existing_perf.daily_snapshots = None

        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = existing_perf

        mock_db_session.get = AsyncMock(return_value=upload)

        await collector.collect_video_performance(upload.id)

        assert existing_perf.daily_snapshots == [
            {
                "date": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
                "views": 1000,
                "likes": 50,
                "engagement_rate": pytest.approx(0.06),
            }
        ]

    @pytest.mark.asyncio
    async def test_collect_upload_not_found_raises(self, collector, mock_db_session):
        """Test error when upload not found."""
        mock_db_session.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Upload not found"):
            await collector.collect_video_performance(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_collect_not_uploaded_raises(self, collector, mock_db_session):
        """Test error when video not uploaded to YouTube."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = None

        mock_db_session.get = AsyncMock(return_value=upload)

        with pytest.raises(ValueError, match="not uploaded to YouTube"):
            await collector.collect_video_performance(upload.id)

    @pytest.mark.asyncio
    async def test_collect_engagement_rate_zero_views(
        self, collector, mock_youtube_api, mock_db_session
    ):
        """Test engagement rate is 0 when views are 0."""
        mock_youtube_api.get_video_analytics = AsyncMock(
            return_value=VideoAnalytics(
                video_id="yt_123",
                views=0,
                likes=0,
                comments=0,
            )
        )

        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.performance = None

        mock_db_session.get = AsyncMock(return_value=upload)

        await collector.collect_video_performance(upload.id)

        added_perf = mock_db_session.add.call_args[0][0]
        assert added_perf.engagement_rate == 0.0

    # =========================================================================
    # sync_channel_uploads() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_sync_channel_uploads_empty(self, collector, mock_db_session):
        """Test sync when no uploads found."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        synced = await collector.sync_channel_uploads(uuid.uuid4())

        assert synced == []

    @pytest.mark.asyncio
    async def test_sync_channel_uploads_collects_each(self, collector, mock_db_session):
        """Test that sync collects performance for each upload."""
        upload1 = MagicMock(spec=Upload)
        upload1.id = uuid.uuid4()
        upload1.youtube_video_id = "yt_1"
        upload1.performance = None

        upload2 = MagicMock(spec=Upload)
        upload2.id = uuid.uuid4()
        upload2.youtube_video_id = "yt_2"
        upload2.performance = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [upload1, upload2]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            collector, "collect_video_performance", new_callable=AsyncMock
        ) as mock_collect:
            mock_collect.return_value = PerformanceSnapshot(views=100)

            synced = await collector.sync_channel_uploads(uuid.uuid4())

        assert len(synced) == 2
        assert mock_collect.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_channel_uploads_handles_individual_failure(
        self, collector, mock_db_session
    ):
        """Test that failure on one upload doesn't stop others."""
        upload1 = MagicMock(spec=Upload)
        upload1.id = uuid.uuid4()
        upload2 = MagicMock(spec=Upload)
        upload2.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [upload1, upload2]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            collector, "collect_video_performance", new_callable=AsyncMock
        ) as mock_collect:
            mock_collect.side_effect = [
                Exception("API error"),
                PerformanceSnapshot(views=200),
            ]

            synced = await collector.sync_channel_uploads(uuid.uuid4())

        # Only second succeeded
        assert len(synced) == 1
        assert synced[0] == upload2.id

    @pytest.mark.asyncio
    async def test_sync_custom_since_days(self, collector, mock_db_session):
        """Test that custom since_days overrides config."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        await collector.sync_channel_uploads(uuid.uuid4(), since_days=7)

        # Should have been called (no error)
        mock_db_session.execute.assert_called_once()

    # =========================================================================
    # identify_high_performers() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_identify_high_performers_empty(self, collector, mock_db_session):
        """Test identification when no performances exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await collector.identify_high_performers(uuid.uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_identify_marks_top_performers(self, collector, mock_db_session):
        """Test that top performers are correctly identified."""
        performances = []
        for i in range(10):
            perf = MagicMock(spec=Performance)
            perf.upload_id = uuid.uuid4()
            perf.views = (i + 1) * 100  # 100 to 1000
            perf.engagement_rate = (i + 1) * 0.01  # 0.01 to 0.10
            perf.is_high_performer = False
            performances.append(perf)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = performances
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await collector.identify_high_performers(uuid.uuid4())

        # With 90th percentile, index 9 should be high performer
        assert len(result) > 0
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_identify_skips_already_marked(self, collector, mock_db_session):
        """Test that already-marked performers are not duplicated."""
        perf = MagicMock(spec=Performance)
        perf.upload_id = uuid.uuid4()
        perf.views = 10000
        perf.engagement_rate = 0.5
        perf.is_high_performer = True  # Already marked

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [perf]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await collector.identify_high_performers(uuid.uuid4())

        # Should not be in result since already marked
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_identify_custom_percentile(self, collector, mock_db_session):
        """Test custom percentile threshold."""
        performances = []
        for i in range(10):
            perf = MagicMock(spec=Performance)
            perf.upload_id = uuid.uuid4()
            perf.views = (i + 1) * 100
            perf.engagement_rate = (i + 1) * 0.01
            perf.is_high_performer = False
            performances.append(perf)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = performances
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Use 50th percentile — should mark more videos
        result = await collector.identify_high_performers(uuid.uuid4(), threshold_percentile=50.0)

        assert len(result) >= 1


class TestYouTubeAnalyticsCollectorInit:
    """Tests for YouTubeAnalyticsCollector initialization."""

    def test_default_config(self):
        """Test initialization with default config."""
        collector = YouTubeAnalyticsCollector(
            youtube_api=AsyncMock(),
            db_session_factory=MagicMock(),
        )

        assert collector.config is not None
        assert collector.config.metrics_lookback_days == 90

    def test_custom_config(self):
        """Test initialization with custom config."""
        config = AnalyticsConfig(metrics_lookback_days=30)
        collector = YouTubeAnalyticsCollector(
            youtube_api=AsyncMock(),
            db_session_factory=MagicMock(),
            config=config,
        )

        assert collector.config.metrics_lookback_days == 30
