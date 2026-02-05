"""Unit tests for analytics Celery tasks."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.upload import Upload, UploadStatus
from app.workers.analytics import (
    ChannelSyncResult,
    HighPerformerResult,
    VideoSyncResult,
    _identify_high_performers_async,
    _sync_channel_analytics_async,
    _sync_video_performance_async,
)


class TestVideoSyncResult:
    """Tests for VideoSyncResult model."""

    def test_basic_instantiation(self):
        """Test creating VideoSyncResult with required fields."""
        result = VideoSyncResult(
            upload_id="test-upload-id",
            youtube_video_id="yt_123",
            synced_at=datetime.now(tz=UTC),
        )

        assert result.upload_id == "test-upload-id"
        assert result.youtube_video_id == "yt_123"
        assert result.views == 0
        assert result.likes == 0
        assert result.engagement_rate == 0.0
        assert result.error is None

    def test_success_result(self):
        """Test successful sync result."""
        result = VideoSyncResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            youtube_video_id="yt_123",
            views=1000,
            likes=50,
            engagement_rate=0.05,
            synced_at=datetime.now(tz=UTC),
        )

        assert result.views == 1000
        assert result.likes == 50
        assert result.engagement_rate == 0.05
        assert result.error is None

    def test_failed_result(self):
        """Test failed sync result."""
        result = VideoSyncResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            youtube_video_id="yt_123",
            views=0,
            likes=0,
            engagement_rate=0.0,
            synced_at=datetime.now(tz=UTC),
            error="API quota exceeded",
        )

        assert result.error == "API quota exceeded"


class TestChannelSyncResult:
    """Tests for ChannelSyncResult model."""

    def test_basic_instantiation(self):
        """Test creating ChannelSyncResult with required fields."""
        result = ChannelSyncResult(
            channel_id="test-channel-id",
            started_at=datetime.now(tz=UTC),
        )

        assert result.channel_id == "test-channel-id"
        assert result.videos_synced == 0
        assert result.videos_failed == 0
        assert result.total_views == 0
        assert result.errors == []

    def test_partial_success(self):
        """Test partial success result."""
        result = ChannelSyncResult(
            channel_id="123e4567-e89b-12d3-a456-426614174000",
            videos_synced=8,
            videos_failed=2,
            total_views=5000,
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
            errors=["Error 1", "Error 2"],
        )

        assert result.videos_synced == 8
        assert result.videos_failed == 2
        assert result.total_views == 5000
        assert len(result.errors) == 2


class TestHighPerformerResult:
    """Tests for HighPerformerResult model."""

    def test_basic_instantiation(self):
        """Test creating HighPerformerResult with required fields."""
        result = HighPerformerResult(
            channel_id="test-channel-id",
            started_at=datetime.now(tz=UTC),
        )

        assert result.channel_id == "test-channel-id"
        assert result.analyzed_count == 0
        assert result.high_performers == 0
        assert result.high_performer_ids == []

    def test_with_performers(self):
        """Test result with high performers."""
        result = HighPerformerResult(
            channel_id="123e4567-e89b-12d3-a456-426614174000",
            analyzed_count=100,
            high_performers=3,
            threshold_views=10000,
            threshold_engagement=0.05,
            high_performer_ids=["upload_1", "upload_2", "upload_3"],
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )

        assert result.high_performers == 3
        assert len(result.high_performer_ids) == 3
        assert result.threshold_views == 10000


class TestSyncVideoPerformanceAsync:
    """Tests for _sync_video_performance_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.analytics.get_container") as mock_get:
            container = MagicMock()

            # Mock analytics collector
            collector = AsyncMock()
            container.services.analytics_collector.return_value = collector

            # Mock session factory
            session = AsyncMock()
            factory = MagicMock()
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock()
            container.infrastructure.db_session_factory.return_value = factory

            mock_get.return_value = container
            yield container, collector, session

    @pytest.mark.asyncio
    async def test_sync_success(self, mock_container):
        """Test successful video sync."""
        container, collector, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock collector response (matching actual implementation)
        collector.collect_video_performance = AsyncMock(
            return_value=MagicMock(
                views=5000,
                likes=200,
                engagement_rate=0.04,
            )
        )

        result = await _sync_video_performance_async(upload_id)

        assert result.views == 5000
        assert result.likes == 200
        assert result.engagement_rate == 0.04
        assert result.error is None

    @pytest.mark.asyncio
    async def test_sync_upload_not_found(self, mock_container):
        """Test sync when upload not found."""
        container, collector, session = mock_container

        upload_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await _sync_video_performance_async(upload_id)

        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_sync_no_youtube_id(self, mock_container):
        """Test sync when no YouTube ID."""
        container, collector, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload without YouTube ID
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = None
        upload.upload_status = UploadStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        result = await _sync_video_performance_async(upload_id)

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sync_api_error(self, mock_container):
        """Test sync handles API errors."""
        container, collector, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock API error
        collector.collect_video_performance = AsyncMock(side_effect=Exception("YouTube API error"))

        result = await _sync_video_performance_async(upload_id)

        assert "YouTube API error" in result.error


class TestSyncChannelAnalyticsAsync:
    """Tests for _sync_channel_analytics_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.analytics.get_container") as mock_get:
            container = MagicMock()

            # Mock analytics collector
            collector = AsyncMock()
            container.services.analytics_collector.return_value = collector

            # Mock session factory
            session = AsyncMock()
            factory = MagicMock()
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock()
            container.infrastructure.db_session_factory.return_value = factory

            mock_get.return_value = container
            yield container, collector, session

    @pytest.mark.asyncio
    async def test_sync_all_uploads(self, mock_container):
        """Test syncing all channel uploads."""
        container, collector, session = mock_container

        channel_id = str(uuid.uuid4())

        # Mock uploads - actual implementation queries uploads directly
        upload1 = MagicMock(spec=Upload)
        upload1.id = uuid.uuid4()
        upload1.youtube_video_id = "yt_1"
        upload2 = MagicMock(spec=Upload)
        upload2.id = uuid.uuid4()
        upload2.youtube_video_id = "yt_2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [upload1, upload2]
        session.execute = AsyncMock(return_value=mock_result)

        # Mock performance collection
        mock_performance = MagicMock()
        mock_performance.views = 500
        collector.collect_video_performance = AsyncMock(return_value=mock_performance)

        result = await _sync_channel_analytics_async(
            channel_id=channel_id,
            days_lookback=30,
        )

        assert result.videos_synced == 2
        assert result.videos_failed == 0
        assert result.total_views == 1000

    @pytest.mark.asyncio
    async def test_sync_partial_failure(self, mock_container):
        """Test sync with some failures."""
        container, collector, session = mock_container

        channel_id = str(uuid.uuid4())

        # Mock uploads
        upload1 = MagicMock(spec=Upload)
        upload1.id = uuid.uuid4()
        upload1.youtube_video_id = "yt_1"
        upload2 = MagicMock(spec=Upload)
        upload2.id = uuid.uuid4()
        upload2.youtube_video_id = "yt_2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [upload1, upload2]
        session.execute = AsyncMock(return_value=mock_result)

        # First succeeds, second fails
        call_count = 0

        async def mock_collect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(views=500)
            raise Exception("API error")

        collector.collect_video_performance = AsyncMock(side_effect=mock_collect)

        result = await _sync_channel_analytics_async(
            channel_id=channel_id,
            days_lookback=30,
        )

        assert result.videos_synced == 1
        assert result.videos_failed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_sync_empty_channel(self, mock_container):
        """Test sync on channel with no uploads."""
        container, collector, session = mock_container

        channel_id = str(uuid.uuid4())

        # No uploads
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await _sync_channel_analytics_async(
            channel_id=channel_id,
            days_lookback=30,
        )

        assert result.videos_synced == 0
        assert result.videos_failed == 0
        assert result.total_views == 0


class TestIdentifyHighPerformersAsync:
    """Tests for _identify_high_performers_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.analytics.get_container") as mock_get:
            container = MagicMock()

            # Mock analytics collector
            collector = AsyncMock()
            container.services.analytics_collector.return_value = collector

            mock_get.return_value = container
            yield container, collector

    @pytest.mark.asyncio
    async def test_identify_performers(self, mock_container):
        """Test identifying high performers."""
        container, collector = mock_container

        channel_id = str(uuid.uuid4())

        # Mock high performers (actual implementation returns Performance objects)
        performer1 = MagicMock()
        performer1.upload_id = uuid.uuid4()
        performer1.views = 10000
        performer1.engagement_rate = 0.08
        performer2 = MagicMock()
        performer2.upload_id = uuid.uuid4()
        performer2.views = 8000
        performer2.engagement_rate = 0.06

        collector.identify_high_performers = AsyncMock(return_value=[performer1, performer2])

        result = await _identify_high_performers_async(
            channel_id=channel_id,
            days_lookback=90,
        )

        assert result.high_performers == 2
        assert len(result.high_performer_ids) == 2

    @pytest.mark.asyncio
    async def test_no_high_performers(self, mock_container):
        """Test when no high performers found."""
        container, collector = mock_container

        channel_id = str(uuid.uuid4())

        collector.identify_high_performers = AsyncMock(return_value=[])

        result = await _identify_high_performers_async(
            channel_id=channel_id,
            days_lookback=90,
        )

        assert result.high_performers == 0
        assert result.high_performer_ids == []

    @pytest.mark.asyncio
    async def test_marks_for_training(self, mock_container):
        """Test that high performers thresholds are captured."""
        container, collector = mock_container

        channel_id = str(uuid.uuid4())

        # Mock high performers with specific thresholds
        performer1 = MagicMock()
        performer1.upload_id = uuid.uuid4()
        performer1.views = 15000
        performer1.engagement_rate = 0.10

        collector.identify_high_performers = AsyncMock(return_value=[performer1])

        result = await _identify_high_performers_async(
            channel_id=channel_id,
            days_lookback=90,
        )

        assert result.high_performers == 1
        assert result.threshold_views == 15000
        assert result.threshold_engagement == 0.10


class TestAnalyticsTasksRetry:
    """Tests for analytics task retry behavior."""

    def test_video_sync_result_serializable(self):
        """Test that VideoSyncResult is serializable for Celery."""
        result = VideoSyncResult(
            upload_id=str(uuid.uuid4()),
            youtube_video_id="yt_123",
            views=100,
            likes=10,
            engagement_rate=0.10,
            synced_at=datetime.now(tz=UTC),
        )

        # Should be able to dump to dict
        data = result.model_dump()
        assert isinstance(data, dict)
        assert data["views"] == 100

    def test_channel_sync_result_serializable(self):
        """Test that ChannelSyncResult is serializable."""
        result = ChannelSyncResult(
            channel_id=str(uuid.uuid4()),
            videos_synced=10,
            videos_failed=2,
            total_views=5000,
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
            errors=["Error 1", "Error 2"],
        )

        data = result.model_dump()
        assert isinstance(data, dict)
        assert data["videos_synced"] == 10

    def test_high_performer_result_serializable(self):
        """Test that HighPerformerResult is serializable."""
        result = HighPerformerResult(
            channel_id=str(uuid.uuid4()),
            analyzed_count=50,
            high_performers=3,
            threshold_views=10000,
            threshold_engagement=0.05,
            high_performer_ids=[str(uuid.uuid4()) for _ in range(3)],
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )

        data = result.model_dump()
        assert isinstance(data, dict)
        assert len(data["high_performer_ids"]) == 3
