"""Unit tests for YouTubeUploader service."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.youtube_upload import YouTubeAPIConfig
from app.core.exceptions import RecordNotFoundError, YouTubeAPIError
from app.infrastructure.youtube_api import UploadResult as APIUploadResult
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video
from app.services.uploader.youtube_uploader import UploadResult, YouTubeUploader


class TestUploadResult:
    """Tests for UploadResult dataclass."""

    def test_basic_instantiation(self):
        """Test basic instantiation."""
        result = UploadResult(
            upload_id=uuid.uuid4(),
            video_id=uuid.uuid4(),
            youtube_video_id="abc123",
            youtube_url="https://youtube.com/watch?v=abc123",
            upload_status=UploadStatus.COMPLETED,
        )

        assert result.youtube_video_id == "abc123"
        assert result.upload_status == UploadStatus.COMPLETED
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed upload result."""
        result = UploadResult(
            upload_id=uuid.uuid4(),
            video_id=uuid.uuid4(),
            youtube_video_id=None,
            youtube_url=None,
            upload_status=UploadStatus.FAILED,
            error_message="API quota exceeded",
        )

        assert result.youtube_video_id is None
        assert result.upload_status == UploadStatus.FAILED
        assert result.error_message == "API quota exceeded"


def create_api_upload_result(video_id: str = "yt_video_123") -> APIUploadResult:
    """Helper to create APIUploadResult with all required fields."""
    return APIUploadResult(
        video_id=video_id,
        url=f"https://youtube.com/watch?v={video_id}",
        status="uploaded",
        processing_status="processing",
        uploaded_at=datetime.now(tz=UTC),
    )


class TestYouTubeUploader:
    """Tests for YouTubeUploader service."""

    @pytest.fixture
    def mock_youtube_api(self):
        """Create mock YouTube API client."""
        api = AsyncMock()
        api.upload_video = AsyncMock(return_value=create_api_upload_result())
        api.get_video_status = AsyncMock(
            return_value={
                "processingDetails": {"processingStatus": "succeeded"},
            }
        )
        api.set_thumbnail = AsyncMock(return_value=True)
        return api

    @pytest.fixture
    def mock_db_session_factory(self):
        """Create mock database session factory."""
        session = AsyncMock()
        session.get = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock()
        return factory, session

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return YouTubeAPIConfig(
            default_category_id="28",
            thumbnail_upload_enabled=True,
        )

    @pytest.fixture
    def uploader(self, mock_youtube_api, mock_db_session_factory, config):
        """Create YouTubeUploader instance."""
        factory, _ = mock_db_session_factory
        return YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
            config=config,
        )

    @pytest.fixture
    def sample_video(self):
        """Create sample video for testing."""
        video = MagicMock(spec=Video)
        video.id = uuid.uuid4()
        video.video_path = "/tmp/test_video.mp4"
        video.thumbnail_path = "/tmp/test_thumb.jpg"
        video.upload = None
        return video

    # =========================================================================
    # upload() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_upload_creates_upload_record(
        self, uploader, mock_db_session_factory, sample_video
    ):
        """Test that upload creates an Upload record when none exists."""
        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=sample_video)

        result = await uploader.upload(
            video_id=sample_video.id,
            title="Test Video",
            description="Test description",
            tags=["tag1", "tag2"],
        )

        assert result.upload_status == UploadStatus.PROCESSING
        assert result.youtube_video_id == "yt_video_123"
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_calls_youtube_api(
        self, uploader, mock_youtube_api, mock_db_session_factory, sample_video
    ):
        """Test that upload calls YouTube API with correct parameters."""
        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=sample_video)

        await uploader.upload(
            video_id=sample_video.id,
            title="My Video Title",
            description="My description",
            tags=["ai", "tech"],
            privacy_status=PrivacyStatus.PRIVATE,
        )

        mock_youtube_api.upload_video.assert_called_once()
        call_args = mock_youtube_api.upload_video.call_args
        metadata = call_args.kwargs["metadata"]
        assert metadata.title == "My Video Title"
        assert metadata.privacy_status == "private"
        assert metadata.is_shorts is True

    @pytest.mark.asyncio
    async def test_upload_video_not_found(self, mock_youtube_api):
        """Test upload raises error when video not found."""
        # Create fresh mocks for this test
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        context_manager = MagicMock()
        context_manager.__aenter__ = AsyncMock(return_value=session)
        context_manager.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=context_manager)

        uploader = YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
        )

        with pytest.raises(RecordNotFoundError) as exc_info:
            await uploader.upload(
                video_id=uuid.uuid4(),
                title="Test",
            )

        assert exc_info.value.model == "Video"

    @pytest.mark.asyncio
    async def test_upload_handles_api_error(
        self, uploader, mock_youtube_api, mock_db_session_factory, sample_video
    ):
        """Test that API errors result in FAILED status."""
        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=sample_video)
        mock_youtube_api.upload_video = AsyncMock(
            side_effect=YouTubeAPIError(message="Quota exceeded", video_id="test")
        )

        result = await uploader.upload(
            video_id=sample_video.id,
            title="Test",
        )

        assert result.upload_status == UploadStatus.FAILED
        assert "Quota exceeded" in result.error_message

    @pytest.mark.asyncio
    async def test_upload_with_scheduled_time(
        self, uploader, mock_db_session_factory, sample_video
    ):
        """Test upload with scheduled publish time."""
        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=sample_video)
        scheduled = datetime.now(tz=UTC)

        result = await uploader.upload(
            video_id=sample_video.id,
            title="Test",
            scheduled_at=scheduled,
        )

        assert result.upload_status == UploadStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_upload_truncates_long_title(
        self, uploader, mock_youtube_api, mock_db_session_factory, sample_video
    ):
        """Test that long titles are truncated to 100 characters."""
        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=sample_video)
        long_title = "A" * 150

        await uploader.upload(
            video_id=sample_video.id,
            title=long_title,
        )

        call_args = mock_youtube_api.upload_video.call_args
        metadata = call_args.kwargs["metadata"]
        assert len(metadata.title) == 100

    @pytest.mark.asyncio
    async def test_upload_without_thumbnail(
        self, uploader, mock_youtube_api, mock_db_session_factory
    ):
        """Test upload when video has no thumbnail."""
        video = MagicMock(spec=Video)
        video.id = uuid.uuid4()
        video.video_path = "/tmp/test.mp4"
        video.thumbnail_path = None
        video.upload = None

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=video)

        await uploader.upload(video_id=video.id, title="Test")

        call_args = mock_youtube_api.upload_video.call_args
        assert call_args.kwargs["thumbnail_path"] is None

    # =========================================================================
    # check_processing_status() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_check_processing_status_completed(
        self, uploader, mock_youtube_api, mock_db_session_factory
    ):
        """Test processing status check when video is processed."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=upload)

        status = await uploader.check_processing_status(upload.id)

        assert status == UploadStatus.COMPLETED
        assert upload.upload_status == UploadStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_check_processing_status_failed(
        self, uploader, mock_youtube_api, mock_db_session_factory
    ):
        """Test processing status check when processing failed."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        mock_youtube_api.get_video_status = AsyncMock(
            return_value={
                "processingDetails": {
                    "processingStatus": "failed",
                    "processingFailureReason": "invalidFile",
                },
            }
        )

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=upload)

        status = await uploader.check_processing_status(upload.id)

        assert status == UploadStatus.FAILED
        assert "invalidFile" in upload.error_message

    @pytest.mark.asyncio
    async def test_check_processing_status_not_found(self, mock_youtube_api):
        """Test processing status check when upload not found."""
        # Create fresh mocks for this test
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.commit = AsyncMock()

        context_manager = MagicMock()
        context_manager.__aenter__ = AsyncMock(return_value=session)
        context_manager.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=context_manager)

        uploader = YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
        )

        with pytest.raises(RecordNotFoundError):
            await uploader.check_processing_status(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_check_processing_status_no_youtube_id(self, uploader, mock_db_session_factory):
        """Test status check when video not yet uploaded to YouTube."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = None
        upload.upload_status = UploadStatus.PENDING

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=upload)

        status = await uploader.check_processing_status(upload.id)

        assert status == UploadStatus.PENDING

    @pytest.mark.asyncio
    async def test_check_processing_status_api_error_graceful(
        self, uploader, mock_youtube_api, mock_db_session_factory
    ):
        """Test that API errors during status check are handled gracefully."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        mock_youtube_api.get_video_status = AsyncMock(
            side_effect=YouTubeAPIError(message="API error", video_id="yt_123")
        )

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=upload)

        status = await uploader.check_processing_status(upload.id)

        # Should return current status without raising
        assert status == UploadStatus.PROCESSING

    # =========================================================================
    # set_thumbnail() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_set_thumbnail_success(self, uploader, mock_youtube_api, mock_db_session_factory):
        """Test successful thumbnail upload."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = "yt_123"

        _, session = mock_db_session_factory
        session.get = AsyncMock(return_value=upload)

        result = await uploader.set_thumbnail(upload.id, Path("/tmp/thumbnail.jpg"))

        assert result is True
        mock_youtube_api.set_thumbnail.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_thumbnail_not_uploaded(self, mock_youtube_api):
        """Test thumbnail upload when video not yet uploaded."""
        upload = MagicMock(spec=Upload)
        upload.id = uuid.uuid4()
        upload.youtube_video_id = None

        # Create fresh mocks for this test
        session = AsyncMock()
        session.get = AsyncMock(return_value=upload)

        context_manager = MagicMock()
        context_manager.__aenter__ = AsyncMock(return_value=session)
        context_manager.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=context_manager)

        uploader = YouTubeUploader(
            youtube_api=mock_youtube_api,
            db_session_factory=factory,
        )

        with pytest.raises(YouTubeAPIError) as exc_info:
            await uploader.set_thumbnail(upload.id, Path("/tmp/thumb.jpg"))

        assert "not yet uploaded" in str(exc_info.value)


class TestYouTubeUploaderIntegration:
    """Integration-style tests for YouTubeUploader."""

    @pytest.mark.asyncio
    async def test_full_upload_flow(self):
        """Test complete upload flow from video to completed status."""
        # Setup mocks
        mock_api = AsyncMock()
        mock_api.upload_video = AsyncMock(return_value=create_api_upload_result("yt_final_123"))
        mock_api.get_video_status = AsyncMock(
            return_value={"processingDetails": {"processingStatus": "succeeded"}}
        )

        video = MagicMock(spec=Video)
        video.id = uuid.uuid4()
        video.video_path = "/videos/final.mp4"
        video.thumbnail_path = "/videos/final_thumb.jpg"
        video.upload = None

        session = AsyncMock()
        session.get = AsyncMock(return_value=video)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock()

        uploader = YouTubeUploader(
            youtube_api=mock_api,
            db_session_factory=factory,
        )

        # Step 1: Upload
        result = await uploader.upload(
            video_id=video.id,
            title="Final Video",
            description="This is the final test",
            tags=["test", "final"],
        )

        assert result.youtube_video_id == "yt_final_123"
        assert result.upload_status == UploadStatus.PROCESSING

        # Step 2: Check processing (simulate upload record retrieval)
        upload = MagicMock(spec=Upload)
        upload.id = result.upload_id
        upload.youtube_video_id = "yt_final_123"
        upload.upload_status = UploadStatus.PROCESSING
        session.get = AsyncMock(return_value=upload)

        final_status = await uploader.check_processing_status(result.upload_id)

        assert final_status == UploadStatus.COMPLETED
