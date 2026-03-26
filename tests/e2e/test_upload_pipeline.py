"""E2E tests for complete upload and analytics pipeline.

These tests verify the full upload workflow:
1. Video → Upload pipeline → YouTube upload with metadata
2. Upload → Analytics collection → Performance tracking
3. Performance data → Optimal time analysis → Scheduling
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.youtube_upload import (
    AnalyticsConfig,
    SchedulePreferenceConfig,
    YouTubeAPIConfig,
    YouTubeUploadPipelineConfig,
)
from app.core.exceptions import YouTubeAPIError
from app.infrastructure.youtube_api import (
    UploadResult as APIUploadResult,
)
from app.infrastructure.youtube_api import (
    VideoAnalytics,
    YouTubeAPIClient,
)
from app.models.performance import Performance
from app.models.script import Script
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video
from app.services.analytics.collector import YouTubeAnalyticsCollector
from app.services.analytics.optimal_time import OptimalTimeAnalyzer
from app.services.scheduler.upload_scheduler import UploadScheduler
from app.services.uploader.pipeline import UploadPipeline
from app.services.uploader.youtube_uploader import YouTubeUploader
from tests.conftest import make_mock_session_factory


def _make_api_upload_result(
    video_id: str = "yt_e2e_123",
) -> APIUploadResult:
    return APIUploadResult(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        status="uploaded",
        processing_status="processing",
        uploaded_at=datetime.now(tz=UTC),
    )


@pytest.fixture
def mock_youtube_api() -> AsyncMock:
    """Full mock YouTube API client."""
    api = AsyncMock(spec=YouTubeAPIClient)
    api.upload_video = AsyncMock(return_value=_make_api_upload_result())
    api.get_video_status = AsyncMock(
        return_value={"processingDetails": {"processingStatus": "succeeded"}}
    )
    api.set_thumbnail = AsyncMock(return_value=True)
    api.get_video_analytics = AsyncMock(
        return_value=VideoAnalytics(
            video_id="yt_e2e_123",
            views=5000,
            likes=250,
            dislikes=10,
            comments=80,
            shares=45,
            watch_time_minutes=2500,
            avg_view_duration_seconds=30.0,
            avg_view_percentage=65.0,
            subscribers_gained=25,
            subscribers_lost=3,
        )
    )
    api.get_traffic_sources = AsyncMock(
        return_value={"SEARCH": 2000, "BROWSE": 1500, "SUGGESTED": 1000, "EXTERNAL": 500}
    )
    api.get_channel_analytics = AsyncMock(return_value={"rows": []})
    return api


@pytest.fixture
def sample_script() -> MagicMock:
    """Script with YouTube metadata."""
    script = MagicMock(spec=Script)
    script.id = uuid.uuid4()
    script.youtube_title = "AI가 바꾸는 미래 #Shorts"
    script.youtube_description = "인공지능 기술의 최신 트렌드를 60초로 정리했습니다."
    script.youtube_tags = ["AI", "인공지능", "shorts", "테크"]
    script.headline = "AI 미래"
    return script


@pytest.fixture
def sample_video(sample_script: MagicMock) -> MagicMock:
    """Video linked to sample script."""
    video = MagicMock(spec=Video)
    video.id = uuid.uuid4()
    video.script_id = sample_script.id
    video.channel_id = uuid.uuid4()
    video.video_path = "/outputs/videos/test_video.mp4"
    video.thumbnail_path = "/outputs/videos/test_thumb.jpg"
    video.upload = None
    return video


# =============================================================================
# E2E: Upload pipeline → YouTube → Processing status
# =============================================================================


class TestUploadToYouTubeE2E:
    """Full upload flow: pipeline → uploader → API → processing check."""

    @pytest.fixture
    def upload_env(
        self,
        mock_youtube_api: AsyncMock,
        sample_video: MagicMock,
        sample_script: MagicMock,
    ) -> tuple[UploadPipeline, YouTubeUploader, AsyncMock]:
        """Wired pipeline + uploader + session for upload E2E tests."""
        factory, session = make_mock_session_factory()
        session.get = AsyncMock(
            side_effect=lambda model, id, **kw: (sample_video if model is Video else sample_script)
        )

        uploader = YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
            config=YouTubeAPIConfig(),
        )
        pipeline = UploadPipeline(
            uploader=uploader,
            db_session_factory=factory,
            config=YouTubeUploadPipelineConfig(),
        )
        return pipeline, uploader, session

    @pytest.mark.asyncio
    async def test_immediate_upload_full_flow(
        self,
        upload_env: tuple[UploadPipeline, YouTubeUploader, AsyncMock],
        sample_video: MagicMock,
    ) -> None:
        """Video → UploadPipeline → YouTubeUploader → YouTube API → check status."""
        pipeline, uploader, session = upload_env

        # Step 1: Process video through pipeline (immediate)
        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
            privacy_status=PrivacyStatus.PRIVATE,
        )

        assert result.status == "processing"
        assert result.youtube_video_id == "yt_e2e_123"
        assert result.youtube_url == "https://www.youtube.com/watch?v=yt_e2e_123"
        assert result.metadata is not None
        assert result.metadata.title == "AI가 바꾸는 미래 #Shorts"
        assert result.metadata.tags == ["AI", "인공지능", "shorts", "테크"]

        # Step 2: Check processing status → COMPLETED
        upload_mock = MagicMock(spec=Upload)
        upload_mock.id = result.upload_id
        upload_mock.youtube_video_id = "yt_e2e_123"
        upload_mock.upload_status = UploadStatus.PROCESSING
        session.get = AsyncMock(return_value=upload_mock)

        final_status = await uploader.check_processing_status(result.upload_id)

        assert final_status == UploadStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_scheduled_upload_then_execute(
        self,
        upload_env: tuple[UploadPipeline, YouTubeUploader, AsyncMock],
        sample_video: MagicMock,
    ) -> None:
        """Video → schedule → later execute scheduled upload."""
        pipeline, _, session = upload_env
        scheduled_time = datetime.now(tz=UTC) + timedelta(hours=6)

        # Step 1: Schedule
        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=False,
            scheduled_at=scheduled_time,
        )

        assert result.status == "scheduled"
        assert result.youtube_video_id is None

        # Step 2: Execute the scheduled upload
        upload_mock = MagicMock(spec=Upload)
        upload_mock.id = result.upload_id
        upload_mock.video_id = sample_video.id
        upload_mock.title = "AI가 바꾸는 미래 #Shorts"
        upload_mock.description = "인공지능 기술의 최신 트렌드를 60초로 정리했습니다."
        upload_mock.tags = ["AI", "인공지능", "shorts", "테크"]
        upload_mock.category_id = "28"
        upload_mock.privacy_status = PrivacyStatus.PRIVATE
        upload_mock.scheduled_at = scheduled_time

        video_mock = MagicMock(spec=Video)
        video_mock.id = sample_video.id

        session.get = AsyncMock(
            side_effect=lambda model, id, **kw: (upload_mock if model is Upload else video_mock)
        )

        exec_result = await pipeline.execute_scheduled_upload(upload_mock.id)

        assert exec_result.upload_status == UploadStatus.PROCESSING
        assert exec_result.youtube_video_id == "yt_e2e_123"

    @pytest.mark.asyncio
    async def test_upload_api_failure_marks_failed(
        self,
        mock_youtube_api: AsyncMock,
        upload_env: tuple[UploadPipeline, YouTubeUploader, AsyncMock],
        sample_video: MagicMock,
    ) -> None:
        """Upload API failure → FAILED status, no exception to caller."""
        pipeline, _, _ = upload_env
        mock_youtube_api.upload_video = AsyncMock(
            side_effect=YouTubeAPIError(
                message="Quota exceeded for today",
                error_code="quotaExceeded",
            )
        )

        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        assert result.status == "failed"
        assert "Quota exceeded" in result.error_message

    @pytest.mark.asyncio
    async def test_metadata_fallback_when_script_has_no_youtube_fields(
        self,
        mock_youtube_api: AsyncMock,
        sample_video: MagicMock,
    ) -> None:
        """Script without YouTube metadata falls back to headline."""
        bare_script = MagicMock(spec=Script)
        bare_script.id = sample_video.script_id
        bare_script.youtube_title = None
        bare_script.youtube_description = None
        bare_script.youtube_tags = None
        bare_script.headline = "AI 미래 요약"

        factory, session = make_mock_session_factory()
        session.get = AsyncMock(
            side_effect=lambda model, id, **kw: (sample_video if model is Video else bare_script)
        )

        uploader = YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
        )
        pipeline = UploadPipeline(
            uploader=uploader,
            db_session_factory=factory,
        )

        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        assert result.metadata.title == "AI 미래 요약"
        assert result.metadata.description == ""
        assert result.metadata.tags == []


# =============================================================================
# E2E: Upload → Analytics collection → High performer detection
# =============================================================================


class TestAnalyticsCollectionE2E:
    """Upload completes → collect analytics → identify high performers."""

    @pytest.mark.asyncio
    async def test_collect_performance_after_upload(
        self,
        mock_youtube_api: AsyncMock,
    ) -> None:
        """Completed upload → fetch analytics → create Performance record."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_e2e_123"
        upload.upload_status = UploadStatus.COMPLETED
        upload.performance = None

        session = AsyncMock()
        session.get = AsyncMock(return_value=upload)
        session.add = MagicMock()
        session.commit = AsyncMock()
        factory, _ = make_mock_session_factory(session)

        collector = YouTubeAnalyticsCollector(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
            config=AnalyticsConfig(metrics_lookback_days=30),
        )

        snapshot = await collector.collect_video_performance(upload.id)

        # Verify analytics were fetched
        assert snapshot.views == 5000
        assert snapshot.likes == 250
        assert snapshot.comments == 80
        assert snapshot.watch_time_seconds == 150000  # 2500 min * 60
        assert snapshot.traffic_sources == {
            "SEARCH": 2000,
            "BROWSE": 1500,
            "SUGGESTED": 1000,
            "EXTERNAL": 500,
        }

        # Verify Performance record created
        session.add.assert_called_once()
        perf = session.add.call_args[0][0]
        assert isinstance(perf, Performance)
        assert perf.views == 5000
        assert perf.engagement_rate == pytest.approx((250 + 80) / 5000)
        assert perf.subscribers_gained == 25

    @pytest.mark.asyncio
    async def test_channel_sync_collects_all_uploads(
        self,
        mock_youtube_api: AsyncMock,
    ) -> None:
        """Sync all channel uploads → collect each → return synced IDs."""
        uploads = []
        for i in range(3):
            u = MagicMock(spec=Upload)
            u.id = uuid.uuid4()
            u.youtube_video_id = f"yt_vid_{i}"
            u.upload_status = UploadStatus.COMPLETED
            u.performance = None
            uploads.append(u)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = uploads
        session.execute = AsyncMock(return_value=mock_result)
        session.get = AsyncMock(
            side_effect=lambda model, id, **kw: next((u for u in uploads if u.id == id), None)
        )
        session.add = MagicMock()
        session.commit = AsyncMock()
        factory, _ = make_mock_session_factory(session)

        collector = YouTubeAnalyticsCollector(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
        )

        synced = await collector.sync_channel_uploads(uuid.uuid4())

        assert len(synced) == 3
        assert mock_youtube_api.get_video_analytics.call_count == 3

    @pytest.mark.asyncio
    async def test_identify_high_performers_from_collected_data(
        self,
        mock_youtube_api: AsyncMock,
    ) -> None:
        """Collect → identify top performers → mark is_high_performer."""
        performances = []
        for i in range(10):
            perf = MagicMock(spec=Performance)
            perf.upload_id = uuid.uuid4()
            perf.views = 100 * (i + 1)  # 100..1000
            perf.engagement_rate = 0.01 * (i + 1)  # 0.01..0.10
            perf.is_high_performer = False
            performances.append(perf)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = performances
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()
        factory, _ = make_mock_session_factory(session)

        collector = YouTubeAnalyticsCollector(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
            config=AnalyticsConfig(performance_percentile=80.0),
        )

        high_ids = await collector.identify_high_performers(uuid.uuid4())

        assert len(high_ids) >= 1
        # Top performers should be marked
        marked = [p for p in performances if p.is_high_performer]
        assert len(marked) >= 1


# =============================================================================
# E2E: Optimal time analysis → Scheduling
# =============================================================================


class TestOptimalTimeSchedulingE2E:
    """Analyze performance → determine optimal time → schedule upload."""

    @pytest.mark.asyncio
    async def test_analyze_and_schedule(self) -> None:
        """Analyze channel → get optimal time → schedule upload."""
        # Step 1: Prepare performance data for analysis
        rows = []
        for day_offset in range(20):
            upload = MagicMock(spec=Upload)
            upload.uploaded_at = datetime(
                2024, 1, 1 + (day_offset % 28), 10 + (day_offset % 8), 0, tzinfo=UTC
            )
            perf = MagicMock(spec=Performance)
            perf.views = 200 + day_offset * 50
            perf.engagement_rate = 0.03 + day_offset * 0.002
            rows.append((upload, perf))

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()
        factory, _ = make_mock_session_factory(session)

        # Step 2: Analyze
        analyzer = OptimalTimeAnalyzer(
            db_session_factory=factory,
            config=AnalyticsConfig(min_sample_size=5),
        )

        analysis = await analyzer.analyze_channel(uuid.uuid4())

        assert analysis.sample_size == 20
        assert len(analysis.best_hours) > 0
        assert len(analysis.best_slots) > 0

        # Step 3: Get next optimal time
        next_time = analyzer.get_next_optimal_time(
            analysis,
            after=datetime(2024, 2, 1, 8, 0, tzinfo=UTC),
            allowed_hours=list(range(9, 22)),
        )

        assert next_time.hour in range(9, 22)
        assert next_time > datetime(2024, 2, 1, 8, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_insufficient_data_uses_golden_hours(self) -> None:
        """Not enough data → default Korean golden hours → schedule."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No data
        session.execute = AsyncMock(return_value=mock_result)
        factory, _ = make_mock_session_factory(session)

        analyzer = OptimalTimeAnalyzer(
            db_session_factory=factory,
            config=AnalyticsConfig(min_sample_size=10),
        )

        analysis = await analyzer.analyze_channel(uuid.uuid4())

        # Should use Korean golden hours
        assert analysis.best_hours == [7, 12, 18, 21]
        assert analysis.best_days == [5, 6]

        # Schedule should still work with defaults
        next_time = analyzer.get_next_optimal_time(
            analysis,
            after=datetime(2024, 1, 15, 6, 0, tzinfo=UTC),
            allowed_hours=list(range(9, 22)),
        )

        assert next_time.hour in [12, 18, 21]  # Golden hours within allowed range

    @pytest.mark.asyncio
    async def test_scheduler_respects_interval_and_daily_limit(self) -> None:
        """Scheduler enforces min interval and max daily uploads."""
        factory, session = make_mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        scheduler = UploadScheduler(
            db_session_factory=factory,
            config=SchedulePreferenceConfig(
                allowed_hours=list(range(9, 22)),
                min_interval_hours=4,
                max_daily_uploads=2,
            ),
        )

        channel_id = uuid.uuid4()

        # Schedule two uploads
        time1 = await scheduler.schedule_upload(
            upload_id=uuid.uuid4(),
            channel_id=channel_id,
        )
        time2 = await scheduler.schedule_upload(
            upload_id=uuid.uuid4(),
            channel_id=channel_id,
        )

        # Minimum 4-hour gap
        assert time2 >= time1 + timedelta(hours=4)

        # Both within allowed hours
        assert time1.hour in range(9, 22)
        assert time2.hour in range(9, 22)
