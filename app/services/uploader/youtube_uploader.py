"""YouTube video upload service.

This module provides the YouTubeUploader service for orchestrating
video uploads to YouTube with database persistence.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.youtube_upload import YouTubeAPIConfig
from app.core.exceptions import RecordNotFoundError, YouTubeAPIError
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.infrastructure.youtube_api import UploadMetadata, YouTubeAPIClient
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video

logger = get_logger(__name__)


@dataclass
class UploadResult:
    """Result of video upload operation.

    Attributes:
        upload_id: Database upload record ID
        video_id: Database video record ID
        youtube_video_id: YouTube's video ID
        youtube_url: Full YouTube URL
        upload_status: Final upload status
        error_message: Error message if failed
        uploaded_at: Upload timestamp
    """

    upload_id: uuid.UUID
    video_id: uuid.UUID
    youtube_video_id: str | None
    youtube_url: str | None
    upload_status: UploadStatus
    error_message: str | None = None
    uploaded_at: datetime | None = None


class YouTubeUploader:
    """Orchestrate video uploads to YouTube with database persistence.

    Handles the full upload workflow including:
    - Loading video from database
    - Uploading to YouTube via API
    - Creating/updating Upload records
    - Thumbnail upload

    Example:
        >>> uploader = YouTubeUploader(youtube_api, db_session_factory)
        >>> result = await uploader.upload(
        ...     video_id=video.id,
        ...     title="My Video",
        ...     description="Description here",
        ...     tags=["tag1", "tag2"],
        ... )
    """

    def __init__(
        self,
        youtube_api: YouTubeAPIClient,
        db_session_factory: SessionFactory,
        config: YouTubeAPIConfig | None = None,
    ) -> None:
        """Initialize YouTube uploader.

        Args:
            youtube_api: YouTube API client
            db_session_factory: Database session factory
            config: Upload configuration
        """
        self.youtube_api = youtube_api
        self.db_session_factory = db_session_factory
        self.config = config or YouTubeAPIConfig()

        logger.info("YouTubeUploader initialized")

    async def upload(
        self,
        video_id: uuid.UUID,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str | None = None,
        privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE,
        scheduled_at: datetime | None = None,
    ) -> UploadResult:
        """Upload video to YouTube.

        Args:
            video_id: Database video ID
            title: Video title
            description: Video description
            tags: Video tags
            category_id: YouTube category ID
            privacy_status: Privacy setting
            scheduled_at: Scheduled publish time

        Returns:
            UploadResult with upload details

        Raises:
            RecordNotFoundError: If video not found
            YouTubeAPIError: If upload fails
        """
        logger.info("Starting upload", video_id=str(video_id), title=title[:50])

        async with self.db_session_factory() as session:
            # Load video
            video = await session.get(Video, video_id)
            if not video:
                raise RecordNotFoundError(model="Video", record_id=str(video_id))

            # Check if upload record exists
            upload = video.upload
            if not upload:
                # Create new upload record
                upload = Upload(
                    video_id=video_id,
                    title=title[:100],
                    description=description[:5000] if description else None,
                    tags=tags,
                    category_id=category_id or self.config.default_category_id,
                    privacy_status=privacy_status,
                    scheduled_at=scheduled_at,
                    upload_status=UploadStatus.UPLOADING,
                )
                session.add(upload)
                await session.flush()

            upload_id = upload.id

            try:
                # Build metadata
                metadata = UploadMetadata(
                    title=title[:100],
                    description=description[:5000] if description else "",
                    tags=tags,
                    category_id=category_id or self.config.default_category_id,
                    privacy_status=privacy_status.value,
                    scheduled_start_time=scheduled_at,
                    is_shorts=True,
                )

                # Upload to YouTube
                video_path = Path(video.video_path)
                thumbnail_path = Path(video.thumbnail_path) if video.thumbnail_path else None

                yt_result = await self.youtube_api.upload_video(
                    video_path=video_path,
                    metadata=metadata,
                    thumbnail_path=thumbnail_path if self.config.thumbnail_upload_enabled else None,
                )

                # Update upload record
                upload.youtube_video_id = yt_result.video_id
                upload.youtube_url = yt_result.url
                upload.uploaded_at = datetime.now(tz=UTC)
                upload.upload_status = UploadStatus.PROCESSING

                await session.commit()

                logger.info(
                    "Upload successful",
                    upload_id=str(upload_id),
                    youtube_id=yt_result.video_id,
                )

                return UploadResult(
                    upload_id=upload_id,
                    video_id=video_id,
                    youtube_video_id=yt_result.video_id,
                    youtube_url=yt_result.url,
                    upload_status=UploadStatus.PROCESSING,
                    uploaded_at=upload.uploaded_at,
                )

            except YouTubeAPIError as e:
                # Update upload status to failed
                upload.upload_status = UploadStatus.FAILED
                upload.error_message = str(e)[:500]
                await session.commit()

                logger.error(
                    "Upload failed",
                    upload_id=str(upload_id),
                    error=str(e),
                )

                return UploadResult(
                    upload_id=upload_id,
                    video_id=video_id,
                    youtube_video_id=None,
                    youtube_url=None,
                    upload_status=UploadStatus.FAILED,
                    error_message=str(e)[:500],
                )

    async def check_processing_status(self, upload_id: uuid.UUID) -> UploadStatus:
        """Check YouTube processing status and update database.

        Args:
            upload_id: Database upload ID

        Returns:
            Current upload status

        Raises:
            RecordNotFoundError: If upload not found
        """
        async with self.db_session_factory() as session:
            upload = await session.get(Upload, upload_id)
            if not upload:
                raise RecordNotFoundError(model="Upload", record_id=str(upload_id))

            if not upload.youtube_video_id:
                return upload.upload_status

            try:
                status = await self.youtube_api.get_video_status(upload.youtube_video_id)

                processing_status = status.get("processingDetails", {}).get(
                    "processingStatus", "unknown"
                )

                if processing_status == "succeeded":
                    upload.upload_status = UploadStatus.COMPLETED
                    upload.published_at = datetime.now(tz=UTC)
                elif processing_status == "failed":
                    upload.upload_status = UploadStatus.FAILED
                    upload.error_message = status.get("processingDetails", {}).get(
                        "processingFailureReason", "Processing failed"
                    )

                await session.commit()
                return upload.upload_status

            except YouTubeAPIError as e:
                logger.warning(
                    "Status check failed",
                    upload_id=str(upload_id),
                    error=str(e),
                )
                return upload.upload_status

    async def set_thumbnail(self, upload_id: uuid.UUID, thumbnail_path: Path) -> bool:
        """Upload custom thumbnail for an uploaded video.

        Args:
            upload_id: Database upload ID
            thumbnail_path: Path to thumbnail image

        Returns:
            True if successful

        Raises:
            RecordNotFoundError: If upload not found
            YouTubeAPIError: If thumbnail upload fails
        """
        async with self.db_session_factory() as session:
            upload = await session.get(Upload, upload_id)
            if not upload:
                raise RecordNotFoundError(model="Upload", record_id=str(upload_id))

            if not upload.youtube_video_id:
                raise YouTubeAPIError(
                    message="Video not yet uploaded to YouTube",
                    video_id=str(upload_id),
                )

            return await self.youtube_api.set_thumbnail(
                upload.youtube_video_id,
                thumbnail_path,
            )


__all__ = [
    "YouTubeUploader",
    "UploadResult",
]
