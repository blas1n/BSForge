"""Upload pipeline service.

This module provides the UploadPipeline that orchestrates the complete
upload workflow using metadata from Script model.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config.youtube_upload import YouTubeUploadPipelineConfig
from app.core.exceptions import RecordNotFoundError
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.script import Script
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video
from app.services.uploader.youtube_uploader import UploadResult, YouTubeUploader

logger = get_logger(__name__)


@dataclass
class VideoMetadata:
    """Video metadata from Script.

    Attributes:
        title: Video title
        description: Video description
        tags: List of tags
        category_id: YouTube category ID
    """

    title: str
    description: str
    tags: list[str]
    category_id: str = "28"  # Science & Technology


@dataclass
class UploadPipelineResult:
    """Result of upload pipeline execution.

    Attributes:
        upload_id: Database upload record ID
        video_id: Database video record ID
        youtube_video_id: YouTube's video ID (if uploaded)
        youtube_url: Full YouTube URL (if uploaded)
        status: Final status
        metadata: Video metadata used
        error_message: Error message if failed
        started_at: Pipeline start time
        completed_at: Pipeline completion time
    """

    upload_id: uuid.UUID | None
    video_id: uuid.UUID
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    status: str = "pending"
    metadata: VideoMetadata | None = None
    error_message: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    completed_at: datetime | None = None


class UploadPipeline:
    """Orchestrate the complete upload process.

    Uses metadata stored in Script model (generated during script creation).

    Example:
        >>> pipeline = UploadPipeline(
        ...     uploader=youtube_uploader,
        ...     db_session_factory=session_factory,
        ... )
        >>> result = await pipeline.process_video(video_id, immediate=True)
    """

    def __init__(
        self,
        uploader: YouTubeUploader,
        db_session_factory: SessionFactory,
        config: YouTubeUploadPipelineConfig | None = None,
    ) -> None:
        """Initialize upload pipeline.

        Args:
            uploader: YouTube uploader service
            db_session_factory: Database session factory
            config: Pipeline configuration
        """
        self.uploader = uploader
        self.db_session_factory = db_session_factory
        self.config = config or YouTubeUploadPipelineConfig()

        logger.info("UploadPipeline initialized")

    async def process_video(
        self,
        video_id: uuid.UUID,
        immediate: bool = False,
        scheduled_at: datetime | None = None,
        privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE,
    ) -> UploadPipelineResult:
        """Process video through the complete upload pipeline.

        Pipeline steps:
        1. Load video and related data from database
        2. Get metadata from Script model
        3. Create upload record
        4. Either upload immediately or schedule for later

        Args:
            video_id: Database video ID
            immediate: If True, upload immediately
            scheduled_at: Scheduled upload time (ignored if immediate=True)
            privacy_status: Privacy setting for upload

        Returns:
            UploadPipelineResult with pipeline results

        Raises:
            RecordNotFoundError: If video not found
        """
        logger.info(
            "Processing video",
            video_id=str(video_id),
            immediate=immediate,
        )

        result = UploadPipelineResult(
            upload_id=None,
            video_id=video_id,
        )

        try:
            async with self.db_session_factory() as session:
                # Load video with relationships
                video = await session.get(Video, video_id)
                if not video:
                    raise RecordNotFoundError(model="Video", record_id=str(video_id))

                # Load script
                script = await session.get(Script, video.script_id)
                if not script:
                    raise RecordNotFoundError(
                        model="Script",
                        record_id=str(video.script_id),
                    )

                # Get metadata from script
                metadata = self._get_metadata_from_script(script)
                result.metadata = metadata

                # Create or update upload record
                upload = video.upload
                if not upload:
                    upload = Upload(
                        video_id=video_id,
                        title=metadata.title,
                        description=metadata.description,
                        tags=metadata.tags,
                        category_id=metadata.category_id,
                        privacy_status=privacy_status,
                        is_shorts=True,
                        upload_status=UploadStatus.PENDING,
                    )
                    session.add(upload)
                    await session.flush()
                else:
                    # Update existing upload with metadata
                    upload.title = metadata.title
                    upload.description = metadata.description
                    upload.tags = metadata.tags

                result.upload_id = upload.id

                if immediate:
                    # Upload immediately
                    upload.upload_status = UploadStatus.UPLOADING
                    await session.commit()

                    upload_result = await self.uploader.upload(
                        video_id=video_id,
                        title=metadata.title,
                        description=metadata.description,
                        tags=metadata.tags,
                        category_id=metadata.category_id,
                        privacy_status=privacy_status,
                    )

                    result.youtube_video_id = upload_result.youtube_video_id
                    result.youtube_url = upload_result.youtube_url
                    result.status = upload_result.upload_status.value
                    result.error_message = upload_result.error_message

                else:
                    # Schedule for later
                    upload.scheduled_at = scheduled_at
                    upload.upload_status = UploadStatus.SCHEDULED
                    await session.commit()

                    result.status = "scheduled"

                result.completed_at = datetime.now(tz=UTC)
                logger.info(
                    "Pipeline completed",
                    video_id=str(video_id),
                    status=result.status,
                    youtube_id=result.youtube_video_id,
                )

                return result

        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Pipeline failed",
                video_id=str(video_id),
                error=str(e),
                exc_info=True,
            )
            result.status = "failed"
            result.error_message = str(e)[:500]
            result.completed_at = datetime.now(tz=UTC)
            return result

    def _get_metadata_from_script(self, script: Script) -> VideoMetadata:
        """Get metadata from Script model.

        Args:
            script: Script record with youtube metadata

        Returns:
            VideoMetadata from script
        """
        return VideoMetadata(
            title=script.youtube_title or script.headline or "Untitled",
            description=script.youtube_description or "",
            tags=list(script.youtube_tags) if script.youtube_tags else [],
            category_id=self.config.youtube_api.default_category_id,
        )

    async def execute_scheduled_upload(self, upload_id: uuid.UUID) -> UploadResult:
        """Execute a scheduled upload.

        Args:
            upload_id: Database upload ID

        Returns:
            UploadResult from the upload

        Raises:
            RecordNotFoundError: If upload not found
        """
        logger.info("Executing scheduled upload", upload_id=str(upload_id))

        async with self.db_session_factory() as session:
            upload = await session.get(Upload, upload_id)
            if not upload:
                raise RecordNotFoundError(model="Upload", record_id=str(upload_id))

            # Get the video
            video = await session.get(Video, upload.video_id)
            if not video:
                raise RecordNotFoundError(model="Video", record_id=str(upload.video_id))

            # Execute upload
            return await self.uploader.upload(
                video_id=upload.video_id,
                title=upload.title,
                description=upload.description or "",
                tags=upload.tags,
                category_id=upload.category_id,
                privacy_status=upload.privacy_status,
                scheduled_at=upload.scheduled_at,
            )


__all__ = [
    "UploadPipeline",
    "UploadPipelineResult",
    "VideoMetadata",
]
