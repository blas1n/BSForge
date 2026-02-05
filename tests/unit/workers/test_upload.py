"""Unit tests for upload Celery tasks."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.upload import Upload, UploadStatus
from app.workers.upload import (
    ProcessingStatusResult,
    ScheduledUploadResult,
    UploadTaskResult,
    _check_processing_status_async,
    _process_scheduled_uploads_async,
    _upload_video_async,
)


class TestUploadTaskResult:
    """Tests for UploadTaskResult model."""

    def test_success_result(self):
        """Test successful upload result."""
        result = UploadTaskResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            video_id="123e4567-e89b-12d3-a456-426614174001",
            youtube_video_id="yt_abc123",
            youtube_url="https://youtube.com/watch?v=yt_abc123",
            status=UploadStatus.PROCESSING.value,
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )

        assert result.youtube_video_id == "yt_abc123"
        assert result.error is None

    def test_failed_result(self):
        """Test failed upload result."""
        result = UploadTaskResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            video_id="123e4567-e89b-12d3-a456-426614174001",
            youtube_video_id=None,
            youtube_url=None,
            status=UploadStatus.FAILED.value,
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
            error="Upload failed: quota exceeded",
        )

        assert result.youtube_video_id is None
        assert result.error == "Upload failed: quota exceeded"


class TestScheduledUploadResult:
    """Tests for ScheduledUploadResult model."""

    def test_empty_result(self):
        """Test empty scheduled upload result."""
        result = ScheduledUploadResult(
            processed_count=0,
            success_count=0,
            failed_count=0,
            results=[],
            started_at=datetime.now(tz=UTC),
        )

        assert result.processed_count == 0
        assert len(result.results) == 0

    def test_mixed_result(self):
        """Test mixed success/failure result."""
        result = ScheduledUploadResult(
            processed_count=3,
            success_count=2,
            failed_count=1,
            results=[
                {"upload_id": "1", "status": "completed"},
                {"upload_id": "2", "status": "completed"},
                {"upload_id": "3", "status": "failed", "error": "API error"},
            ],
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )

        assert result.success_count == 2
        assert result.failed_count == 1


class TestProcessingStatusResult:
    """Tests for ProcessingStatusResult model."""

    def test_processing_result(self):
        """Test processing status result."""
        result = ProcessingStatusResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            youtube_video_id="yt_123",
            processing_status="processing",
            upload_status=UploadStatus.PROCESSING.value,
        )

        assert result.processing_status == "processing"
        assert result.error is None

    def test_completed_result(self):
        """Test completed status result."""
        result = ProcessingStatusResult(
            upload_id="123e4567-e89b-12d3-a456-426614174000",
            youtube_video_id="yt_123",
            processing_status="succeeded",
            upload_status=UploadStatus.COMPLETED.value,
        )

        assert result.processing_status == "succeeded"


class TestUploadVideoAsync:
    """Tests for _upload_video_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.upload.get_container") as mock_get:
            container = MagicMock()

            # Mock uploader
            uploader = AsyncMock()
            uploader.upload = AsyncMock()
            container.services.youtube_uploader.return_value = uploader

            # Mock session factory
            session = AsyncMock()
            session.execute = AsyncMock()
            factory = MagicMock()
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock()
            container.infrastructure.db_session_factory.return_value = factory

            mock_get.return_value = container
            yield container, uploader, session

    @pytest.mark.asyncio
    async def test_upload_video_success(self, mock_container):
        """Test successful video upload."""
        container, uploader, session = mock_container

        upload_id = str(uuid.uuid4())
        video_id = uuid.uuid4()

        # Mock upload record lookup
        upload = MagicMock(spec=Upload)
        upload.video_id = video_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock uploader result
        uploader.upload = AsyncMock(
            return_value=MagicMock(
                youtube_video_id="yt_success",
                youtube_url="https://youtube.com/watch?v=yt_success",
                status=UploadStatus.PROCESSING,
            )
        )

        result = await _upload_video_async(
            upload_id=upload_id,
            video_path="/videos/test.mp4",
        )

        assert result.youtube_video_id == "yt_success"
        assert result.status == UploadStatus.PROCESSING.value

    @pytest.mark.asyncio
    async def test_upload_video_not_found(self, mock_container):
        """Test upload when record not found."""
        container, uploader, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock no upload record found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await _upload_video_async(
            upload_id=upload_id,
            video_path="/videos/test.mp4",
        )

        assert result.status == UploadStatus.FAILED.value
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_upload_video_exception(self, mock_container):
        """Test upload handles exceptions gracefully."""
        container, uploader, session = mock_container

        upload_id = str(uuid.uuid4())
        video_id = uuid.uuid4()

        # Mock upload record
        upload = MagicMock(spec=Upload)
        upload.video_id = video_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock uploader to raise exception
        uploader.upload = AsyncMock(side_effect=Exception("Connection error"))

        result = await _upload_video_async(
            upload_id=upload_id,
            video_path="/videos/test.mp4",
        )

        assert result.status == UploadStatus.FAILED.value
        assert "Connection error" in result.error


class TestProcessScheduledUploadsAsync:
    """Tests for _process_scheduled_uploads_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.upload.get_container") as mock_get:
            container = MagicMock()

            # Mock scheduler
            scheduler = AsyncMock()
            scheduler.get_pending_uploads = AsyncMock(return_value=[])
            container.services.upload_scheduler.return_value = scheduler

            # Mock uploader
            uploader = AsyncMock()
            container.services.youtube_uploader.return_value = uploader

            # Mock session factory
            session = AsyncMock()
            factory = MagicMock()
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock()
            container.infrastructure.db_session_factory.return_value = factory

            mock_get.return_value = container
            yield container, scheduler, uploader, session

    @pytest.mark.asyncio
    async def test_no_pending_uploads(self, mock_container):
        """Test when no pending uploads."""
        container, scheduler, uploader, session = mock_container
        scheduler.get_pending_uploads = AsyncMock(return_value=[])

        result = await _process_scheduled_uploads_async(limit=10)

        assert result.processed_count == 0
        assert result.success_count == 0
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_process_multiple_uploads(self, mock_container):
        """Test processing multiple pending uploads."""
        container, scheduler, uploader, session = mock_container

        # Mock pending uploads
        pending = [
            MagicMock(upload_id=uuid.uuid4(), channel_id=uuid.uuid4()),
            MagicMock(upload_id=uuid.uuid4(), channel_id=uuid.uuid4()),
        ]
        scheduler.get_pending_uploads = AsyncMock(return_value=pending)

        # Mock upload records
        def make_upload(upload_id):
            upload = MagicMock(spec=Upload)
            upload.id = upload_id
            video = MagicMock()
            video.output_path = "/videos/test.mp4"
            upload.video = video
            return upload

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            make_upload(pending[0].upload_id),
            make_upload(pending[1].upload_id),
        ]
        session.execute = AsyncMock(return_value=mock_result)

        # Mock uploader success
        uploader.upload = AsyncMock(
            return_value=MagicMock(
                youtube_video_id="yt_123",
                status=UploadStatus.COMPLETED,
            )
        )

        result = await _process_scheduled_uploads_async(limit=10)

        assert result.processed_count == 2

    @pytest.mark.asyncio
    async def test_respects_limit(self, mock_container):
        """Test that limit parameter is respected."""
        container, scheduler, uploader, session = mock_container

        scheduler.get_pending_uploads = AsyncMock(return_value=[])

        await _process_scheduled_uploads_async(limit=5)

        scheduler.get_pending_uploads.assert_called_once_with(limit=5)


class TestCheckProcessingStatusAsync:
    """Tests for _check_processing_status_async function."""

    @pytest.fixture
    def mock_container(self):
        """Create mock container."""
        with patch("app.workers.upload.get_container") as mock_get:
            container = MagicMock()

            # Mock YouTube API
            youtube_api = AsyncMock()
            container.infrastructure.youtube_api.return_value = youtube_api

            # Mock session factory
            session = AsyncMock()
            factory = MagicMock()
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock()
            container.infrastructure.db_session_factory.return_value = factory

            mock_get.return_value = container
            yield container, youtube_api, session

    @pytest.mark.asyncio
    async def test_processing_succeeded(self, mock_container):
        """Test status check when processing succeeded."""
        container, youtube_api, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock YouTube API response
        youtube_api.get_video_status = AsyncMock(
            return_value={"processingDetails": {"processingStatus": "succeeded"}}
        )

        result = await _check_processing_status_async(upload_id)

        assert result.processing_status == "succeeded"
        assert result.upload_status == UploadStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_processing_still_ongoing(self, mock_container):
        """Test status check when still processing."""
        container, youtube_api, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock YouTube API - still processing
        youtube_api.get_video_status = AsyncMock(
            return_value={"processingDetails": {"processingStatus": "processing"}}
        )

        result = await _check_processing_status_async(upload_id)

        assert result.processing_status == "processing"

    @pytest.mark.asyncio
    async def test_upload_not_found(self, mock_container):
        """Test status check when upload not found."""
        container, youtube_api, session = mock_container

        upload_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await _check_processing_status_async(upload_id)

        assert result.upload_status == UploadStatus.FAILED.value
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_youtube_id(self, mock_container):
        """Test status check when no YouTube ID yet."""
        container, youtube_api, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload without YouTube ID
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = None
        upload.upload_status = UploadStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        result = await _check_processing_status_async(upload_id)

        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_api_error_handled(self, mock_container):
        """Test that API errors are handled gracefully."""
        container, youtube_api, session = mock_container

        upload_id = str(uuid.uuid4())

        # Mock upload
        upload = MagicMock(spec=Upload)
        upload.youtube_video_id = "yt_123"
        upload.upload_status = UploadStatus.PROCESSING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = upload
        session.execute = AsyncMock(return_value=mock_result)

        # Mock API error
        youtube_api.get_video_status = AsyncMock(side_effect=Exception("API unavailable"))

        result = await _check_processing_status_async(upload_id)

        assert result.processing_status == "error"
        assert "API unavailable" in result.error
