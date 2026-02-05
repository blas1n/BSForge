"""YouTube upload Celery tasks.

This module defines Celery tasks for YouTube video uploads:
- upload_video: Upload single video to YouTube
- process_scheduled_uploads: Process pending scheduled uploads
- check_processing_status: Poll YouTube for processing completion
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from pydantic import BaseModel
from sqlalchemy import select

from app.core.container import get_container
from app.models.upload import Upload, UploadStatus

logger = get_task_logger(__name__)


class UploadTaskResult(BaseModel):
    """Result of upload task.

    Attributes:
        upload_id: Database upload ID
        video_id: Database video ID
        youtube_video_id: YouTube video ID (if successful)
        youtube_url: YouTube URL (if successful)
        status: Upload status
        started_at: Task start time
        completed_at: Task completion time
        error: Error message (if failed)
    """

    upload_id: str
    video_id: str
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class ScheduledUploadResult(BaseModel):
    """Result of scheduled upload processing.

    Attributes:
        processed_count: Number of uploads processed
        success_count: Number of successful uploads
        failed_count: Number of failed uploads
        results: Individual upload results
        started_at: Task start time
        completed_at: Task completion time
    """

    processed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    results: list[dict[str, Any]] = []
    started_at: datetime
    completed_at: datetime | None = None


class ProcessingStatusResult(BaseModel):
    """Result of processing status check.

    Attributes:
        upload_id: Upload ID
        youtube_video_id: YouTube video ID
        processing_status: Current processing status
        upload_status: Updated upload status
        error: Error message (if any)
    """

    upload_id: str
    youtube_video_id: str
    processing_status: str
    upload_status: str
    error: str | None = None


async def _upload_video_async(
    upload_id: str,
    video_path: str,
    thumbnail_path: str | None = None,
) -> UploadTaskResult:
    """Upload video to YouTube.

    Args:
        upload_id: Database upload ID
        video_path: Path to video file
        thumbnail_path: Optional path to thumbnail

    Returns:
        UploadTaskResult with status
    """
    from pathlib import Path

    started_at = datetime.now(tz=UTC)

    container = get_container()
    uploader = container.services.youtube_uploader()
    db_session_factory = container.infrastructure.db_session_factory()

    # Get video_id from upload record
    video_id: str | None = None
    async with db_session_factory() as session:
        result = await session.execute(select(Upload).where(Upload.id == uuid.UUID(upload_id)))
        upload = result.scalar_one_or_none()
        if upload:
            video_id = str(upload.video_id)

    if not video_id:
        return UploadTaskResult(
            upload_id=upload_id,
            video_id="",
            status=UploadStatus.FAILED.value,
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
            error="Upload record not found",
        )

    try:
        upload_result = await uploader.upload(
            upload_id=uuid.UUID(upload_id),
            video_path=Path(video_path),
            thumbnail_path=Path(thumbnail_path) if thumbnail_path else None,
        )

        return UploadTaskResult(
            upload_id=upload_id,
            video_id=video_id,
            youtube_video_id=upload_result.youtube_video_id,
            youtube_url=upload_result.youtube_url,
            status=upload_result.status.value,
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
        )

    except Exception as e:
        logger.error(f"Upload failed for {upload_id}: {e}", exc_info=True)
        return UploadTaskResult(
            upload_id=upload_id,
            video_id=video_id,
            status=UploadStatus.FAILED.value,
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
            error=str(e),
        )


async def _process_scheduled_uploads_async(
    limit: int = 10,
) -> ScheduledUploadResult:
    """Process pending scheduled uploads.

    Args:
        limit: Maximum uploads to process

    Returns:
        ScheduledUploadResult with statistics
    """
    started_at = datetime.now(tz=UTC)
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    container = get_container()
    scheduler = container.services.upload_scheduler()
    uploader = container.services.youtube_uploader()
    db_session_factory = container.infrastructure.db_session_factory()

    # Get pending uploads
    pending = await scheduler.get_pending_uploads(limit=limit)

    for entry in pending:
        try:
            # Get video path from database
            async with db_session_factory() as session:
                result = await session.execute(select(Upload).where(Upload.id == entry.upload_id))
                upload = result.scalar_one_or_none()

                if not upload:
                    logger.warning(f"Upload not found: {entry.upload_id}")
                    continue

                # Get video path
                video_path = upload.video.output_path if upload.video else None

                if not video_path:
                    logger.warning(f"Video path not found for upload: {entry.upload_id}")
                    # Update status to failed
                    upload.upload_status = UploadStatus.FAILED
                    upload.error_message = "Video file path not found"
                    await session.commit()
                    failed_count += 1
                    continue

            # Execute upload
            from pathlib import Path

            upload_result = await uploader.upload(
                upload_id=entry.upload_id,
                video_path=Path(video_path),
            )

            results.append(
                {
                    "upload_id": str(entry.upload_id),
                    "youtube_video_id": upload_result.youtube_video_id,
                    "status": upload_result.status.value,
                }
            )

            if upload_result.status == UploadStatus.COMPLETED:
                success_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Failed to process upload {entry.upload_id}: {e}", exc_info=True)
            results.append(
                {
                    "upload_id": str(entry.upload_id),
                    "status": UploadStatus.FAILED.value,
                    "error": str(e),
                }
            )
            failed_count += 1

    return ScheduledUploadResult(
        processed_count=len(pending),
        success_count=success_count,
        failed_count=failed_count,
        results=results,
        started_at=started_at,
        completed_at=datetime.now(tz=UTC),
    )


async def _check_processing_status_async(
    upload_id: str,
) -> ProcessingStatusResult:
    """Check YouTube processing status for an upload.

    Args:
        upload_id: Database upload ID

    Returns:
        ProcessingStatusResult with status
    """
    container = get_container()
    youtube_api = container.infrastructure.youtube_api()
    db_session_factory = container.infrastructure.db_session_factory()

    async with db_session_factory() as session:
        result = await session.execute(select(Upload).where(Upload.id == uuid.UUID(upload_id)))
        upload = result.scalar_one_or_none()

        if not upload or not upload.youtube_video_id:
            return ProcessingStatusResult(
                upload_id=upload_id,
                youtube_video_id="",
                processing_status="unknown",
                upload_status=UploadStatus.FAILED.value,
                error="Upload or YouTube video ID not found",
            )

        try:
            status = await youtube_api.get_video_status(upload.youtube_video_id)
            processing_status = status.get("processingDetails", {}).get(
                "processingStatus", "unknown"
            )

            # Update upload status if processing complete
            if processing_status == "succeeded":
                upload.upload_status = UploadStatus.COMPLETED
                await session.commit()

            return ProcessingStatusResult(
                upload_id=upload_id,
                youtube_video_id=upload.youtube_video_id,
                processing_status=processing_status,
                upload_status=upload.upload_status.value,
            )

        except Exception as e:
            logger.error(
                f"Failed to check processing status for {upload_id}: {e}",
                exc_info=True,
            )
            return ProcessingStatusResult(
                upload_id=upload_id,
                youtube_video_id=upload.youtube_video_id,
                processing_status="error",
                upload_status=upload.upload_status.value,
                error=str(e),
            )


# =============================================================================
# Celery Tasks
# =============================================================================


@shared_task(
    bind=True,
    name="app.workers.upload.upload_video",
    max_retries=3,
    default_retry_delay=60,
)
def upload_video(
    self,
    upload_id: str,
    video_path: str,
    thumbnail_path: str | None = None,
) -> dict[str, Any]:
    """Upload video to YouTube.

    Args:
        self: Celery task instance
        upload_id: Database upload ID
        video_path: Path to video file
        thumbnail_path: Optional path to thumbnail

    Returns:
        UploadTaskResult as dict
    """
    logger.info(f"Starting upload for: {upload_id}")

    try:
        result = asyncio.run(
            _upload_video_async(
                upload_id=upload_id,
                video_path=video_path,
                thumbnail_path=thumbnail_path,
            )
        )

        if result.error:
            logger.error(f"Upload failed: {result.error}")
        else:
            logger.info(f"Upload complete: {upload_id} -> {result.youtube_video_id}")

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Upload task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.upload.process_scheduled_uploads",
    max_retries=2,
    default_retry_delay=300,
)
def process_scheduled_uploads(
    self,
    limit: int = 10,
) -> dict[str, Any]:
    """Process pending scheduled uploads.

    This task should run on a fixed schedule (e.g., every 5 minutes)
    to check for and process uploads that are due.

    Args:
        self: Celery task instance
        limit: Maximum uploads to process in one run

    Returns:
        ScheduledUploadResult as dict
    """
    logger.info("Processing scheduled uploads")

    try:
        result = asyncio.run(_process_scheduled_uploads_async(limit=limit))

        logger.info(
            f"Processed {result.processed_count} uploads: "
            f"{result.success_count} success, {result.failed_count} failed"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Scheduled upload processing failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.upload.check_processing_status",
    max_retries=5,
    default_retry_delay=30,
)
def check_processing_status(
    self,
    upload_id: str,
) -> dict[str, Any]:
    """Check YouTube processing status for an upload.

    This task can be scheduled after upload to poll for processing completion.

    Args:
        self: Celery task instance
        upload_id: Database upload ID

    Returns:
        ProcessingStatusResult as dict
    """
    logger.info(f"Checking processing status for: {upload_id}")

    try:
        result = asyncio.run(_check_processing_status_async(upload_id))

        logger.info(f"Processing status for {upload_id}: {result.processing_status}")

        # Retry if still processing
        if result.processing_status == "processing":
            logger.info(f"Video still processing, will retry: {upload_id}")
            raise self.retry(countdown=60)

        return result.model_dump()

    except Exception as exc:
        if isinstance(exc, self.retry.__class__):
            raise
        logger.error(f"Processing status check failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


__all__ = [
    "upload_video",
    "process_scheduled_uploads",
    "check_processing_status",
    "UploadTaskResult",
    "ScheduledUploadResult",
    "ProcessingStatusResult",
]
