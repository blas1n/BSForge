"""Unit tests for YouTube API client."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from app.core.exceptions import QuotaExceededError, YouTubeAPIError
from app.infrastructure.youtube_api import (
    UploadMetadata,
    UploadResult,
    VideoAnalytics,
    YouTubeAPIClient,
)


def _sync_to_thread(f, *a, **kw):
    """Helper to mock asyncio.to_thread for synchronous execution."""
    return f(*a, **kw) if callable(f) else f


class TestUploadMetadata:
    """Tests for UploadMetadata model."""

    def test_basic_metadata(self):
        """Test basic metadata creation."""
        metadata = UploadMetadata(
            title="Test Video",
            description="Test description",
            tags=["tag1", "tag2"],
            category_id="28",
            privacy_status="private",
        )

        assert metadata.title == "Test Video"
        assert metadata.privacy_status == "private"
        assert metadata.is_shorts is True  # default

    def test_scheduled_metadata(self):
        """Test metadata with scheduled time."""
        scheduled = datetime.now(tz=UTC)
        metadata = UploadMetadata(
            title="Scheduled Video",
            description="",
            tags=[],
            category_id="28",
            privacy_status="private",
            scheduled_start_time=scheduled,
        )

        assert metadata.scheduled_start_time == scheduled

    def test_metadata_defaults(self):
        """Test metadata default values."""
        metadata = UploadMetadata(title="Video")

        assert metadata.is_shorts is True
        assert metadata.tags is None
        assert metadata.description == ""
        assert metadata.category_id == "28"
        assert metadata.privacy_status == "private"


class TestUploadResult:
    """Tests for UploadResult model."""

    def test_success_result(self):
        """Test successful upload result."""
        now = datetime.now(tz=UTC)
        result = UploadResult(
            video_id="yt_abc123",
            url="https://youtube.com/watch?v=yt_abc123",
            status="uploaded",
            processing_status="processing",
            uploaded_at=now,
        )

        assert result.video_id == "yt_abc123"
        assert "yt_abc123" in result.url
        assert result.status == "uploaded"
        assert result.processing_status == "processing"
        assert result.uploaded_at == now


class TestVideoAnalytics:
    """Tests for VideoAnalytics model."""

    def test_basic_analytics(self):
        """Test basic analytics creation."""
        analytics = VideoAnalytics(video_id="vid123")

        assert analytics.video_id == "vid123"
        assert analytics.views == 0
        assert analytics.likes == 0

    def test_full_analytics(self):
        """Test analytics with all fields."""
        analytics = VideoAnalytics(
            video_id="vid123",
            views=10000,
            likes=500,
            dislikes=10,
            comments=100,
            shares=50,
            watch_time_minutes=5000,
            avg_view_duration_seconds=45.5,
            avg_view_percentage=75.0,
            subscribers_gained=20,
            subscribers_lost=2,
        )

        assert analytics.views == 10000
        assert analytics.likes == 500
        assert analytics.avg_view_duration_seconds == 45.5


class TestYouTubeAPIClient:
    """Tests for YouTubeAPIClient."""

    @pytest.fixture
    def mock_auth_client(self):
        """Create mock auth client."""
        auth = AsyncMock()
        auth.get_youtube_service = AsyncMock()
        auth.get_analytics_service = AsyncMock()
        return auth

    @pytest.fixture
    def client(self, mock_auth_client):
        """Create YouTube API client."""
        return YouTubeAPIClient(auth_client=mock_auth_client)

    @pytest.fixture
    def sample_metadata(self):
        """Create sample upload metadata."""
        return UploadMetadata(
            title="Test Video Title",
            description="Test description",
            tags=["test", "video"],
            category_id="28",
            privacy_status="private",
            is_shorts=True,
        )

    # =========================================================================
    # Initialization tests
    # =========================================================================

    def test_init_defaults(self, mock_auth_client):
        """Test default initialization."""
        client = YouTubeAPIClient(auth_client=mock_auth_client)

        assert client.chunk_size == 1024 * 1024
        assert client.max_retries == 3

    def test_init_custom_values(self, mock_auth_client):
        """Test custom initialization values."""
        client = YouTubeAPIClient(
            auth_client=mock_auth_client,
            chunk_size=512 * 1024,
            max_retries=5,
        )

        assert client.chunk_size == 512 * 1024
        assert client.max_retries == 5

    # =========================================================================
    # _build_video_body() tests
    # =========================================================================

    def test_build_video_body_basic(self, client, sample_metadata):
        """Test building video body with basic metadata."""
        body = client._build_video_body(sample_metadata)

        assert body["snippet"]["title"] == "Test Video Title"
        assert body["snippet"]["description"] == "Test description"
        assert body["snippet"]["tags"] == ["test", "video"]
        assert body["snippet"]["categoryId"] == "28"
        assert body["status"]["privacyStatus"] == "private"

    def test_build_video_body_with_schedule(self, client):
        """Test building video body with scheduled time."""
        scheduled = datetime.now(tz=UTC)
        metadata = UploadMetadata(
            title="Scheduled Video",
            scheduled_start_time=scheduled,
        )

        body = client._build_video_body(metadata)

        assert body["status"]["publishAt"] == scheduled.isoformat()
        assert body["status"]["privacyStatus"] == "private"

    def test_build_video_body_truncates_tags(self, client):
        """Test that too many tags are truncated."""
        metadata = UploadMetadata(
            title="Test",
            tags=["tag"] * 600,  # More than 500
        )

        body = client._build_video_body(metadata)

        assert len(body["snippet"]["tags"]) == 500

    # =========================================================================
    # upload_video() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_upload_video_file_not_found(self, client, sample_metadata):
        """Test upload raises error when file not found."""
        with pytest.raises(YouTubeAPIError) as exc_info:
            await client.upload_video(
                video_path=Path("/nonexistent/video.mp4"),
                metadata=sample_metadata,
            )

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_upload_video_success(self, client, mock_auth_client, sample_metadata, tmp_path):
        """Test successful video upload."""
        # Create temp video file
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        # Mock YouTube service
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk = MagicMock(
            return_value=(None, {"id": "yt_uploaded_123", "status": {}})
        )
        mock_service.videos.return_value.insert.return_value = mock_request
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            result = await client.upload_video(
                video_path=video_file,
                metadata=sample_metadata,
            )

        assert result.video_id == "yt_uploaded_123"
        assert "yt_uploaded_123" in result.url

    @pytest.mark.asyncio
    async def test_upload_video_with_thumbnail(
        self, client, mock_auth_client, sample_metadata, tmp_path
    ):
        """Test upload with thumbnail."""
        # Create temp files
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")
        thumb_file = tmp_path / "thumb.jpg"
        thumb_file.write_bytes(b"fake image")

        # Mock YouTube service
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk = MagicMock(return_value=(None, {"id": "yt_123", "status": {}}))
        mock_service.videos.return_value.insert.return_value = mock_request
        mock_service.thumbnails.return_value.set.return_value.execute = MagicMock()
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            result = await client.upload_video(
                video_path=video_file,
                metadata=sample_metadata,
                thumbnail_path=thumb_file,
            )

        assert result.video_id == "yt_123"

    @pytest.mark.asyncio
    async def test_upload_video_quota_exceeded(
        self, client, mock_auth_client, sample_metadata, tmp_path
    ):
        """Test upload raises QuotaExceededError."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        # Mock 403 quota exceeded error
        mock_resp = MagicMock()
        mock_resp.status = 403
        http_error = HttpError(resp=mock_resp, content=b"quotaExceeded")

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk = MagicMock(side_effect=http_error)
        mock_service.videos.return_value.insert.return_value = mock_request
        mock_auth_client.get_youtube_service.return_value = mock_service

        with (
            patch("asyncio.to_thread", side_effect=_sync_to_thread),
            pytest.raises(QuotaExceededError),
        ):
            await client.upload_video(
                video_path=video_file,
                metadata=sample_metadata,
            )

    @pytest.mark.asyncio
    async def test_upload_video_retries_on_503(
        self, client, mock_auth_client, sample_metadata, tmp_path
    ):
        """Test that upload retries on 503 errors."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        # First call raises 503, second succeeds
        call_count = [0]

        def next_chunk_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                resp = MagicMock()
                resp.status = 503
                raise HttpError(resp, b"Service Unavailable")
            return (None, {"id": "yt_retry_success", "status": {}})

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk = next_chunk_side_effect
        mock_service.videos.return_value.insert.return_value = mock_request
        mock_auth_client.get_youtube_service.return_value = mock_service

        with (
            patch("asyncio.to_thread", side_effect=_sync_to_thread),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.upload_video(
                video_path=video_file,
                metadata=sample_metadata,
            )

        assert result.video_id == "yt_retry_success"
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_upload_video_max_retries_exceeded(
        self, client, mock_auth_client, sample_metadata, tmp_path
    ):
        """Test that upload fails after max retries."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        def always_fail():
            resp = MagicMock()
            resp.status = 503
            raise HttpError(resp, b"Service Unavailable")

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk = always_fail
        mock_service.videos.return_value.insert.return_value = mock_request
        mock_auth_client.get_youtube_service.return_value = mock_service

        with (
            patch("asyncio.to_thread", side_effect=_sync_to_thread),
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(YouTubeAPIError),
        ):
            await client.upload_video(
                video_path=video_file,
                metadata=sample_metadata,
            )

    # =========================================================================
    # get_video_status() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_video_status_succeeded(self, client, mock_auth_client):
        """Test getting video status when processing succeeded."""
        mock_service = MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "yt_123",
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            status = await client.get_video_status("yt_123")

        assert status["processingDetails"]["processingStatus"] == "succeeded"

    @pytest.mark.asyncio
    async def test_get_video_status_processing(self, client, mock_auth_client):
        """Test getting video status when still processing."""
        mock_service = MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "yt_123",
                    "processingDetails": {"processingStatus": "processing"},
                }
            ]
        }
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            status = await client.get_video_status("yt_123")

        assert status["processingDetails"]["processingStatus"] == "processing"

    @pytest.mark.asyncio
    async def test_get_video_status_failed(self, client, mock_auth_client):
        """Test getting video status when processing failed."""
        mock_service = MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "yt_123",
                    "processingDetails": {
                        "processingStatus": "failed",
                        "processingFailureReason": "invalidFile",
                    },
                }
            ]
        }
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            status = await client.get_video_status("yt_123")

        assert status["processingDetails"]["processingStatus"] == "failed"

    @pytest.mark.asyncio
    async def test_get_video_status_not_found(self, client, mock_auth_client):
        """Test getting status for non-existent video."""
        mock_service = MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {"items": []}
        mock_auth_client.get_youtube_service.return_value = mock_service

        with (
            patch("asyncio.to_thread", side_effect=_sync_to_thread),
            pytest.raises(YouTubeAPIError) as exc_info,
        ):
            await client.get_video_status("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    # =========================================================================
    # get_video_analytics() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_video_analytics(self, client, mock_auth_client):
        """Test getting video analytics."""
        mock_analytics = MagicMock()
        mock_analytics.reports.return_value.query.return_value.execute.return_value = {
            "rows": [[1000, 50, 5, 20, 10, 500, 30.5, 65.0, 5, 1]]
        }
        mock_auth_client.get_analytics_service.return_value = mock_analytics

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            analytics = await client.get_video_analytics(
                video_id="yt_123",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        assert analytics.views == 1000
        assert analytics.likes == 50

    @pytest.mark.asyncio
    async def test_get_video_analytics_no_data(self, client, mock_auth_client):
        """Test getting analytics when no data available."""
        mock_analytics = MagicMock()
        mock_analytics.reports.return_value.query.return_value.execute.return_value = {"rows": []}
        mock_auth_client.get_analytics_service.return_value = mock_analytics

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            analytics = await client.get_video_analytics(
                video_id="yt_123",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        assert analytics.views == 0
        assert analytics.likes == 0

    # =========================================================================
    # set_thumbnail() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_set_thumbnail_success(self, client, mock_auth_client, tmp_path):
        """Test successful thumbnail upload."""
        thumb_file = tmp_path / "thumb.jpg"
        thumb_file.write_bytes(b"fake image")

        mock_service = MagicMock()
        mock_service.thumbnails.return_value.set.return_value.execute = MagicMock()
        mock_auth_client.get_youtube_service.return_value = mock_service

        with patch("asyncio.to_thread", side_effect=_sync_to_thread):
            result = await client.set_thumbnail("yt_123", thumb_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_thumbnail_video_not_found(self, client, mock_auth_client, tmp_path):
        """Test thumbnail upload for non-existent video."""
        thumb_file = tmp_path / "thumb.jpg"
        thumb_file.write_bytes(b"fake image")

        mock_resp = MagicMock()
        mock_resp.status = 404
        http_error = HttpError(resp=mock_resp, content=b"Video not found")

        mock_service = MagicMock()
        mock_service.thumbnails.return_value.set.return_value.execute.side_effect = http_error
        mock_auth_client.get_youtube_service.return_value = mock_service

        with (
            patch("asyncio.to_thread", side_effect=_sync_to_thread),
            pytest.raises(YouTubeAPIError),
        ):
            await client.set_thumbnail("nonexistent", thumb_file)
