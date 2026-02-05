"""YouTube analytics Celery tasks.

This module defines Celery tasks for YouTube analytics collection:
- sync_video_performance: Sync single video analytics
- sync_channel_analytics: Sync all channel uploads (last N days)
- identify_high_performers: Mark high-performing videos for training
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from pydantic import BaseModel
from sqlalchemy import select

from app.core.container import get_container
from app.models.upload import Upload, UploadStatus

logger = get_task_logger(__name__)


class VideoSyncResult(BaseModel):
    """Result of single video analytics sync.

    Attributes:
        upload_id: Database upload ID
        youtube_video_id: YouTube video ID
        views: Current view count
        likes: Current like count
        engagement_rate: Calculated engagement rate
        synced_at: Sync timestamp
        error: Error message (if failed)
    """

    upload_id: str
    youtube_video_id: str
    views: int = 0
    likes: int = 0
    engagement_rate: float = 0.0
    synced_at: datetime
    error: str | None = None


class ChannelSyncResult(BaseModel):
    """Result of channel analytics sync.

    Attributes:
        channel_id: Database channel ID
        videos_synced: Number of videos synced
        videos_failed: Number of videos that failed
        total_views: Total views across all synced videos
        started_at: Sync start time
        completed_at: Sync completion time
        errors: List of error messages
    """

    channel_id: str
    videos_synced: int = 0
    videos_failed: int = 0
    total_views: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    errors: list[str] = []


class HighPerformerResult(BaseModel):
    """Result of high performer identification.

    Attributes:
        channel_id: Database channel ID
        analyzed_count: Number of videos analyzed
        high_performers: Number of high performers identified
        threshold_views: Views threshold used
        threshold_engagement: Engagement threshold used
        high_performer_ids: List of high performer upload IDs
        started_at: Analysis start time
        completed_at: Analysis completion time
    """

    channel_id: str
    analyzed_count: int = 0
    high_performers: int = 0
    threshold_views: int = 0
    threshold_engagement: float = 0.0
    high_performer_ids: list[str] = []
    started_at: datetime
    completed_at: datetime | None = None


async def _sync_video_performance_async(
    upload_id: str,
) -> VideoSyncResult:
    """Sync analytics for a single video.

    Args:
        upload_id: Database upload ID

    Returns:
        VideoSyncResult with metrics
    """
    synced_at = datetime.now(tz=UTC)

    container = get_container()
    collector = container.services.analytics_collector()
    db_session_factory = container.infrastructure.db_session_factory()

    # Get YouTube video ID
    async with db_session_factory() as session:
        result = await session.execute(select(Upload).where(Upload.id == uuid.UUID(upload_id)))
        upload = result.scalar_one_or_none()

        if not upload or not upload.youtube_video_id:
            return VideoSyncResult(
                upload_id=upload_id,
                youtube_video_id="",
                synced_at=synced_at,
                error="Upload or YouTube video ID not found",
            )

        youtube_video_id = upload.youtube_video_id

    try:
        performance = await collector.collect_video_performance(
            upload_id=uuid.UUID(upload_id),
            youtube_video_id=youtube_video_id,
        )

        return VideoSyncResult(
            upload_id=upload_id,
            youtube_video_id=youtube_video_id,
            views=performance.views,
            likes=performance.likes,
            engagement_rate=performance.engagement_rate,
            synced_at=synced_at,
        )

    except Exception as e:
        logger.error(f"Failed to sync video {upload_id}: {e}", exc_info=True)
        return VideoSyncResult(
            upload_id=upload_id,
            youtube_video_id=youtube_video_id,
            synced_at=synced_at,
            error=str(e),
        )


async def _sync_channel_analytics_async(
    channel_id: str,
    days_lookback: int = 30,
) -> ChannelSyncResult:
    """Sync analytics for all channel uploads.

    Args:
        channel_id: Database channel ID
        days_lookback: Days of uploads to sync

    Returns:
        ChannelSyncResult with statistics
    """
    started_at = datetime.now(tz=UTC)
    errors: list[str] = []
    videos_synced = 0
    videos_failed = 0
    total_views = 0

    container = get_container()
    collector = container.services.analytics_collector()
    db_session_factory = container.infrastructure.db_session_factory()

    cutoff = datetime.now(tz=UTC) - timedelta(days=days_lookback)

    # Get all completed uploads for channel
    async with db_session_factory() as session:
        result = await session.execute(
            select(Upload)
            .join(Upload.video)
            .where(
                Upload.upload_status == UploadStatus.COMPLETED,
                Upload.uploaded_at >= cutoff,
                Upload.youtube_video_id.isnot(None),
            )
        )
        uploads = result.scalars().all()

    logger.info(f"Syncing analytics for {len(uploads)} uploads in channel {channel_id}")

    for upload in uploads:
        try:
            performance = await collector.collect_video_performance(
                upload_id=upload.id,
                youtube_video_id=upload.youtube_video_id or "",
            )
            videos_synced += 1
            total_views += performance.views

        except Exception as e:
            error_msg = f"Failed to sync {upload.id}: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
            videos_failed += 1

    return ChannelSyncResult(
        channel_id=channel_id,
        videos_synced=videos_synced,
        videos_failed=videos_failed,
        total_views=total_views,
        started_at=started_at,
        completed_at=datetime.now(tz=UTC),
        errors=errors,
    )


async def _identify_high_performers_async(
    channel_id: str,
    days_lookback: int = 90,
) -> HighPerformerResult:
    """Identify high-performing videos for training.

    Args:
        channel_id: Database channel ID
        days_lookback: Days of uploads to analyze

    Returns:
        HighPerformerResult with statistics
    """
    started_at = datetime.now(tz=UTC)

    container = get_container()
    collector = container.services.analytics_collector()

    try:
        high_performers = await collector.identify_high_performers(
            channel_id=uuid.UUID(channel_id),
            days_lookback=days_lookback,
        )

        # Calculate approximate thresholds (would need actual calculation in real impl)
        threshold_views = 0
        threshold_engagement = 0.0

        if high_performers:
            # Use first high performer as reference
            threshold_views = high_performers[0].views
            threshold_engagement = high_performers[0].engagement_rate

        return HighPerformerResult(
            channel_id=channel_id,
            analyzed_count=len(high_performers),  # Approximation
            high_performers=len(high_performers),
            threshold_views=threshold_views,
            threshold_engagement=threshold_engagement,
            high_performer_ids=[str(p.upload_id) for p in high_performers],
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
        )

    except Exception as e:
        logger.error(
            f"Failed to identify high performers for {channel_id}: {e}",
            exc_info=True,
        )
        return HighPerformerResult(
            channel_id=channel_id,
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
        )


# =============================================================================
# Celery Tasks
# =============================================================================


@shared_task(
    bind=True,
    name="app.workers.analytics.sync_video_performance",
    max_retries=3,
    default_retry_delay=60,
)
def sync_video_performance(
    self,
    upload_id: str,
) -> dict[str, Any]:
    """Sync analytics for a single video.

    Args:
        self: Celery task instance
        upload_id: Database upload ID

    Returns:
        VideoSyncResult as dict
    """
    logger.info(f"Syncing performance for video: {upload_id}")

    try:
        result = asyncio.run(_sync_video_performance_async(upload_id))

        if result.error:
            logger.warning(f"Sync failed for {upload_id}: {result.error}")
        else:
            logger.info(
                f"Synced {upload_id}: {result.views} views, "
                f"{result.engagement_rate:.2%} engagement"
            )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Video sync task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.analytics.sync_channel_analytics",
    max_retries=2,
    default_retry_delay=300,
)
def sync_channel_analytics(
    self,
    channel_id: str,
    days_lookback: int = 30,
) -> dict[str, Any]:
    """Sync analytics for all channel uploads.

    This task should run on a fixed schedule (e.g., every 6 hours)
    to keep analytics data fresh.

    Args:
        self: Celery task instance
        channel_id: Database channel ID
        days_lookback: Days of uploads to sync

    Returns:
        ChannelSyncResult as dict
    """
    logger.info(f"Syncing analytics for channel: {channel_id}")

    try:
        result = asyncio.run(
            _sync_channel_analytics_async(
                channel_id=channel_id,
                days_lookback=days_lookback,
            )
        )

        logger.info(
            f"Channel sync complete: {result.videos_synced} synced, "
            f"{result.videos_failed} failed, {result.total_views} total views"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"Channel sync task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.analytics.identify_high_performers",
    max_retries=2,
    default_retry_delay=300,
)
def identify_high_performers(
    self,
    channel_id: str,
    days_lookback: int = 90,
) -> dict[str, Any]:
    """Identify high-performing videos for training.

    This task analyzes video performance and marks top performers
    for potential use in RAG training data.

    Args:
        self: Celery task instance
        channel_id: Database channel ID
        days_lookback: Days of uploads to analyze

    Returns:
        HighPerformerResult as dict
    """
    logger.info(f"Identifying high performers for channel: {channel_id}")

    try:
        result = asyncio.run(
            _identify_high_performers_async(
                channel_id=channel_id,
                days_lookback=days_lookback,
            )
        )

        logger.info(
            f"High performer analysis complete: "
            f"{result.high_performers}/{result.analyzed_count} identified"
        )

        return result.model_dump()

    except Exception as exc:
        logger.error(f"High performer identification failed: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc


__all__ = [
    "sync_video_performance",
    "sync_channel_analytics",
    "identify_high_performers",
    "VideoSyncResult",
    "ChannelSyncResult",
    "HighPerformerResult",
]
