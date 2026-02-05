"""Unit tests for UploadPipeline service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.youtube_upload import YouTubeUploadPipelineConfig
from app.core.exceptions import RecordNotFoundError
from app.models.script import Script
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video
from app.services.uploader.pipeline import (
    UploadPipeline,
    UploadPipelineResult,
    VideoMetadata,
)
from app.services.uploader.youtube_uploader import UploadResult


class TestVideoMetadata:
    """Tests for VideoMetadata dataclass."""

    def test_basic_instantiation(self):
        """Test creating VideoMetadata with required fields."""
        metadata = VideoMetadata(
            title="Test Video",
            description="Test description",
            tags=["tag1", "tag2"],
        )

        assert metadata.title == "Test Video"
        assert metadata.description == "Test description"
        assert metadata.tags == ["tag1", "tag2"]
        assert metadata.category_id == "28"  # Default

    def test_custom_category_id(self):
        """Test creating VideoMetadata with custom category ID."""
        metadata = VideoMetadata(
            title="Test",
            description="",
            tags=[],
            category_id="22",
        )

        assert metadata.category_id == "22"


class TestUploadPipelineResult:
    """Tests for UploadPipelineResult dataclass."""

    def test_basic_instantiation(self):
        """Test creating result with required fields."""
        video_id = uuid.uuid4()
        result = UploadPipelineResult(
            upload_id=None,
            video_id=video_id,
        )

        assert result.video_id == video_id
        assert result.upload_id is None
        assert result.status == "pending"
        assert result.youtube_video_id is None
        assert result.youtube_url is None
        assert result.error_message is None

    def test_success_result(self):
        """Test successful pipeline result."""
        video_id = uuid.uuid4()
        upload_id = uuid.uuid4()
        result = UploadPipelineResult(
            upload_id=upload_id,
            video_id=video_id,
            youtube_video_id="yt_123",
            youtube_url="https://youtube.com/watch?v=yt_123",
            status="processing",
        )

        assert result.status == "processing"
        assert result.youtube_video_id == "yt_123"
        assert result.error_message is None

    def test_scheduled_result(self):
        """Test scheduled pipeline result."""
        video_id = uuid.uuid4()
        upload_id = uuid.uuid4()
        result = UploadPipelineResult(
            upload_id=upload_id,
            video_id=video_id,
            status="scheduled",
        )

        assert result.status == "scheduled"

    def test_failed_result(self):
        """Test failed pipeline result."""
        video_id = uuid.uuid4()
        result = UploadPipelineResult(
            upload_id=None,
            video_id=video_id,
            status="failed",
            error_message="Video file not found",
        )

        assert result.status == "failed"
        assert result.error_message == "Video file not found"

    def test_timestamps(self):
        """Test that timestamps are set correctly."""
        video_id = uuid.uuid4()
        result = UploadPipelineResult(
            upload_id=None,
            video_id=video_id,
        )

        assert result.started_at is not None
        assert result.completed_at is None


class TestUploadPipeline:
    """Tests for UploadPipeline service."""

    @pytest.fixture
    def mock_uploader(self):
        """Create mock YouTubeUploader."""
        uploader = AsyncMock()
        uploader.upload = AsyncMock(
            return_value=UploadResult(
                upload_id=uuid.uuid4(),
                video_id=uuid.uuid4(),
                youtube_video_id="yt_video_abc",
                youtube_url="https://youtube.com/watch?v=yt_video_abc",
                upload_status=UploadStatus.PROCESSING,
            )
        )
        return uploader

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_db_session_factory(self, mock_db_session):
        """Create mock database session factory."""
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return factory

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return YouTubeUploadPipelineConfig()

    @pytest.fixture
    def pipeline(self, mock_uploader, mock_db_session_factory, config):
        """Create UploadPipeline instance."""
        return UploadPipeline(
            uploader=mock_uploader,
            db_session_factory=mock_db_session_factory,
            config=config,
        )

    @pytest.fixture
    def sample_script(self):
        """Create sample script with YouTube metadata."""
        script = MagicMock(spec=Script)
        script.id = uuid.uuid4()
        script.youtube_title = "AI Technology Explained"
        script.youtube_description = "Learn about AI in 60 seconds"
        script.youtube_tags = ["AI", "tech", "shorts"]
        script.headline = "AI Tech"
        return script

    @pytest.fixture
    def sample_video(self, sample_script):
        """Create sample video for testing."""
        video = MagicMock(spec=Video)
        video.id = uuid.uuid4()
        video.video_path = "/videos/test.mp4"
        video.thumbnail_path = "/videos/test_thumb.jpg"
        video.script_id = sample_script.id
        video.upload = None  # No existing upload
        video.channel_id = uuid.uuid4()
        return video

    # =========================================================================
    # Initialization tests
    # =========================================================================

    def test_init(self, mock_uploader, mock_db_session_factory, config):
        """Test pipeline initialization."""
        pipeline = UploadPipeline(
            uploader=mock_uploader,
            db_session_factory=mock_db_session_factory,
            config=config,
        )

        assert pipeline.uploader == mock_uploader
        assert pipeline.config == config

    def test_init_default_config(self, mock_uploader, mock_db_session_factory):
        """Test pipeline with default config."""
        pipeline = UploadPipeline(
            uploader=mock_uploader,
            db_session_factory=mock_db_session_factory,
        )

        assert pipeline.config is not None

    # =========================================================================
    # process_video() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_process_video_immediate_upload(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test immediate video upload."""
        # Setup: video found, script found
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        assert result.status == "processing"
        assert result.youtube_video_id == "yt_video_abc"
        mock_uploader.upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_uses_script_metadata(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test that pipeline uses metadata from Script."""
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        call_kwargs = mock_uploader.upload.call_args.kwargs
        assert call_kwargs["title"] == "AI Technology Explained"
        assert call_kwargs["description"] == "Learn about AI in 60 seconds"
        assert call_kwargs["tags"] == ["AI", "tech", "shorts"]

    @pytest.mark.asyncio
    async def test_process_video_not_found(self, pipeline, mock_db_session):
        """Test error when video not found."""
        mock_db_session.get = AsyncMock(return_value=None)

        with pytest.raises(RecordNotFoundError):
            await pipeline.process_video(
                video_id=uuid.uuid4(),
                immediate=True,
            )

    @pytest.mark.asyncio
    async def test_process_video_script_not_found(self, pipeline, mock_db_session, sample_video):
        """Test error when script not found."""
        # Video found but script not found
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else None
        )

        with pytest.raises(RecordNotFoundError):
            await pipeline.process_video(
                video_id=sample_video.id,
                immediate=True,
            )

    @pytest.mark.asyncio
    async def test_process_video_no_script_metadata(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test fallback when script has no YouTube metadata."""
        sample_script.youtube_title = None
        sample_script.youtube_description = None
        sample_script.youtube_tags = None

        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        # Should use fallback values
        call_kwargs = mock_uploader.upload.call_args.kwargs
        assert call_kwargs["title"] == "AI Tech"  # Fallback to headline
        assert call_kwargs["description"] == ""
        assert call_kwargs["tags"] == []

    @pytest.mark.asyncio
    async def test_process_video_scheduled(
        self, pipeline, mock_db_session, sample_video, sample_script
    ):
        """Test scheduled video upload."""
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )
        scheduled_time = datetime.now(tz=UTC)

        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=False,
            scheduled_at=scheduled_time,
        )

        assert result.status == "scheduled"

    @pytest.mark.asyncio
    async def test_process_video_privacy_setting(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test privacy status is passed correctly."""
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
            privacy_status=PrivacyStatus.PUBLIC,
        )

        call_kwargs = mock_uploader.upload.call_args.kwargs
        assert call_kwargs["privacy_status"] == PrivacyStatus.PUBLIC

    @pytest.mark.asyncio
    async def test_process_video_handles_upload_error(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test error handling when upload fails."""
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )
        mock_uploader.upload = AsyncMock(
            return_value=UploadResult(
                upload_id=uuid.uuid4(),
                video_id=sample_video.id,
                youtube_video_id=None,
                youtube_url=None,
                upload_status=UploadStatus.FAILED,
                error_message="API quota exceeded",
            )
        )

        result = await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        assert result.status == "failed"
        assert "quota" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_video_creates_upload_record(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test that upload record is created."""
        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        # Mock flush to set the upload id
        async def mock_flush():
            # Get the upload that was added
            if mock_db_session.add.call_args:
                upload = mock_db_session.add.call_args[0][0]
                if hasattr(upload, "id") and upload.id is None:
                    upload.id = uuid.uuid4()

        mock_db_session.flush = AsyncMock(side_effect=mock_flush)

        await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        # Session.add should be called with Upload instance
        mock_db_session.add.assert_called_once()
        # Upload record should have been added
        added_upload = mock_db_session.add.call_args[0][0]
        assert isinstance(added_upload, Upload)

    @pytest.mark.asyncio
    async def test_process_video_updates_existing_upload(
        self, pipeline, mock_uploader, mock_db_session, sample_video, sample_script
    ):
        """Test that existing upload is updated."""
        # Create existing upload
        existing_upload = MagicMock(spec=Upload)
        existing_upload.id = uuid.uuid4()
        sample_video.upload = existing_upload

        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: sample_video if model == Video else sample_script
        )

        await pipeline.process_video(
            video_id=sample_video.id,
            immediate=True,
        )

        # Session.add should not be called (existing upload)
        mock_db_session.add.assert_not_called()
        # Existing upload should be updated
        assert existing_upload.title == "AI Technology Explained"


class TestUploadPipelineGetMetadata:
    """Tests for _get_metadata_from_script method."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline with mocks."""
        return UploadPipeline(
            uploader=AsyncMock(),
            db_session_factory=MagicMock(),
        )

    def test_get_metadata_full(self, pipeline):
        """Test getting metadata when all fields present."""
        script = MagicMock()
        script.youtube_title = "Full Title"
        script.youtube_description = "Full Description"
        script.youtube_tags = ["tag1", "tag2"]
        script.headline = "Headline"

        metadata = pipeline._get_metadata_from_script(script)

        assert metadata.title == "Full Title"
        assert metadata.description == "Full Description"
        assert metadata.tags == ["tag1", "tag2"]

    def test_get_metadata_fallback_title(self, pipeline):
        """Test fallback to headline when youtube_title is None."""
        script = MagicMock()
        script.youtube_title = None
        script.youtube_description = "Description"
        script.youtube_tags = ["tag"]
        script.headline = "Fallback Headline"

        metadata = pipeline._get_metadata_from_script(script)

        assert metadata.title == "Fallback Headline"

    def test_get_metadata_fallback_untitled(self, pipeline):
        """Test fallback to 'Untitled' when all title options are None."""
        script = MagicMock()
        script.youtube_title = None
        script.youtube_description = None
        script.youtube_tags = None
        script.headline = None

        metadata = pipeline._get_metadata_from_script(script)

        assert metadata.title == "Untitled"
        assert metadata.description == ""
        assert metadata.tags == []


class TestUploadPipelineExecuteScheduled:
    """Tests for execute_scheduled_upload method."""

    @pytest.fixture
    def mock_uploader(self):
        """Create mock uploader."""
        uploader = AsyncMock()
        uploader.upload = AsyncMock(
            return_value=UploadResult(
                upload_id=uuid.uuid4(),
                video_id=uuid.uuid4(),
                youtube_video_id="yt_123",
                youtube_url="https://youtube.com/watch?v=yt_123",
                upload_status=UploadStatus.PROCESSING,
            )
        )
        return uploader

    @pytest.fixture
    def mock_db_session(self):
        """Create mock session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_db_session_factory(self, mock_db_session):
        """Create mock factory."""
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return factory

    @pytest.fixture
    def pipeline(self, mock_uploader, mock_db_session_factory):
        """Create pipeline."""
        return UploadPipeline(
            uploader=mock_uploader,
            db_session_factory=mock_db_session_factory,
        )

    @pytest.mark.asyncio
    async def test_execute_scheduled_upload_success(self, pipeline, mock_uploader, mock_db_session):
        """Test successful scheduled upload execution."""
        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()

        upload = MagicMock(spec=Upload)
        upload.id = upload_id
        upload.video_id = video_id
        upload.title = "Test Title"
        upload.description = "Test Description"
        upload.tags = ["tag1"]
        upload.category_id = "28"
        upload.privacy_status = PrivacyStatus.PRIVATE
        upload.scheduled_at = None

        video = MagicMock(spec=Video)
        video.id = video_id

        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: upload if model == Upload else video
        )

        result = await pipeline.execute_scheduled_upload(upload_id)

        assert result.youtube_video_id == "yt_123"
        mock_uploader.upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_scheduled_upload_not_found(self, pipeline, mock_db_session):
        """Test error when upload not found."""
        mock_db_session.get = AsyncMock(return_value=None)

        with pytest.raises(RecordNotFoundError):
            await pipeline.execute_scheduled_upload(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_execute_scheduled_video_not_found(self, pipeline, mock_db_session):
        """Test error when video not found."""
        upload = MagicMock(spec=Upload)
        upload.video_id = uuid.uuid4()

        mock_db_session.get = AsyncMock(
            side_effect=lambda model, id: upload if model == Upload else None
        )

        with pytest.raises(RecordNotFoundError):
            await pipeline.execute_scheduled_upload(uuid.uuid4())
