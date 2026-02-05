"""YouTube analytics collection service.

This module provides the YouTubeAnalyticsCollector for fetching and storing
video performance metrics from YouTube Analytics API.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config.youtube_upload import AnalyticsConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.infrastructure.youtube_api import YouTubeAPIClient
from app.models.performance import Performance
from app.models.upload import Upload, UploadStatus

logger = get_logger(__name__)


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance data.

    Attributes:
        views: Total view count
        likes: Total likes
        dislikes: Total dislikes
        comments: Total comments
        shares: Total shares
        watch_time_seconds: Total watch time in seconds
        avg_view_duration: Average view duration in seconds
        avg_view_percentage: Average percentage of video watched
        ctr: Click-through rate
        subscribers_gained: Subscribers gained from this video
        subscribers_lost: Subscribers lost from this video
        traffic_sources: Traffic source breakdown
        demographics: Viewer demographics
        collected_at: Collection timestamp
    """

    views: int = 0
    likes: int = 0
    dislikes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_seconds: int = 0
    avg_view_duration: float = 0.0
    avg_view_percentage: float = 0.0
    ctr: float = 0.0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    traffic_sources: dict[str, Any] | None = None
    demographics: dict[str, Any] | None = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class YouTubeAnalyticsCollector:
    """Collect video and channel analytics from YouTube.

    Fetches performance metrics from YouTube Analytics API and
    stores them in the database for analysis.

    Example:
        >>> collector = YouTubeAnalyticsCollector(youtube_api, db_session_factory)
        >>> snapshot = await collector.collect_video_performance(upload_id)
        >>> print(f"Views: {snapshot.views}")
    """

    def __init__(
        self,
        youtube_api: YouTubeAPIClient,
        db_session_factory: SessionFactory,
        config: AnalyticsConfig | None = None,
    ) -> None:
        """Initialize analytics collector.

        Args:
            youtube_api: YouTube API client
            db_session_factory: Database session factory
            config: Analytics configuration
        """
        self.youtube_api = youtube_api
        self.db_session_factory = db_session_factory
        self.config = config or AnalyticsConfig()

        logger.info("YouTubeAnalyticsCollector initialized")

    async def collect_video_performance(
        self,
        upload_id: uuid.UUID,
    ) -> PerformanceSnapshot:
        """Fetch and store performance for a single video.

        Args:
            upload_id: Database upload ID

        Returns:
            PerformanceSnapshot with current metrics

        Raises:
            ValueError: If upload not found or not uploaded
        """
        logger.debug("Collecting performance", upload_id=str(upload_id))

        async with self.db_session_factory() as session:
            # Load upload with performance
            upload = await session.get(
                Upload,
                upload_id,
                options=[selectinload(Upload.performance)],
            )

            if not upload:
                raise ValueError(f"Upload not found: {upload_id}")

            if not upload.youtube_video_id:
                raise ValueError(f"Video not uploaded to YouTube: {upload_id}")

            # Calculate date range
            end_date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            start_date = (
                datetime.now(tz=UTC) - timedelta(days=self.config.metrics_lookback_days)
            ).strftime("%Y-%m-%d")

            # Fetch analytics from YouTube
            analytics = await self.youtube_api.get_video_analytics(
                video_id=upload.youtube_video_id,
                start_date=start_date,
                end_date=end_date,
            )

            # Fetch traffic sources
            traffic_sources = await self.youtube_api.get_traffic_sources(
                video_id=upload.youtube_video_id,
                start_date=start_date,
                end_date=end_date,
            )

            # Create snapshot
            snapshot = PerformanceSnapshot(
                views=analytics.views,
                likes=analytics.likes,
                dislikes=analytics.dislikes,
                comments=analytics.comments,
                shares=analytics.shares,
                watch_time_seconds=analytics.watch_time_minutes * 60,
                avg_view_duration=analytics.avg_view_duration_seconds,
                avg_view_percentage=analytics.avg_view_percentage,
                subscribers_gained=analytics.subscribers_gained,
                subscribers_lost=analytics.subscribers_lost,
                traffic_sources=traffic_sources,
            )

            # Calculate engagement rate
            engagement_rate = 0.0
            if snapshot.views > 0:
                engagement_rate = (snapshot.likes + snapshot.comments) / snapshot.views

            # Update or create performance record
            performance = upload.performance
            if not performance:
                performance = Performance(upload_id=upload_id)
                session.add(performance)

            # Update performance fields
            performance.views = snapshot.views
            performance.likes = snapshot.likes
            performance.dislikes = snapshot.dislikes
            performance.comments = snapshot.comments
            performance.shares = snapshot.shares
            performance.watch_time_seconds = snapshot.watch_time_seconds
            performance.avg_view_duration = snapshot.avg_view_duration
            performance.avg_view_percentage = snapshot.avg_view_percentage
            performance.engagement_rate = engagement_rate
            performance.subscribers_gained = snapshot.subscribers_gained
            performance.subscribers_lost = snapshot.subscribers_lost
            performance.traffic_sources = snapshot.traffic_sources
            performance.last_synced_at = datetime.now(tz=UTC)

            # Append to daily snapshots
            daily_snapshot = {
                "date": end_date,
                "views": snapshot.views,
                "likes": snapshot.likes,
                "engagement_rate": engagement_rate,
            }
            if performance.daily_snapshots:
                performance.daily_snapshots.append(daily_snapshot)
            else:
                performance.daily_snapshots = [daily_snapshot]

            await session.commit()

            logger.info(
                "Performance collected",
                upload_id=str(upload_id),
                views=snapshot.views,
            )

            return snapshot

    async def sync_channel_uploads(
        self,
        channel_id: uuid.UUID,
        since_days: int | None = None,
    ) -> list[uuid.UUID]:
        """Sync performance for all recent uploads in a channel.

        Args:
            channel_id: Database channel ID
            since_days: Days to look back (default from config)

        Returns:
            List of upload IDs that were synced
        """
        since_days = since_days or self.config.metrics_lookback_days
        cutoff = datetime.now(tz=UTC) - timedelta(days=since_days)

        logger.info(
            "Syncing channel uploads",
            channel_id=str(channel_id),
            since_days=since_days,
        )

        async with self.db_session_factory() as session:
            # Find all completed uploads for the channel
            result = await session.execute(
                select(Upload)
                .join(Upload.video)
                .where(
                    Upload.upload_status == UploadStatus.COMPLETED,
                    Upload.youtube_video_id.isnot(None),
                    Upload.uploaded_at >= cutoff,
                )
            )
            uploads = result.scalars().all()

            synced_ids: list[uuid.UUID] = []
            for upload in uploads:
                try:
                    await self.collect_video_performance(upload.id)
                    synced_ids.append(upload.id)
                except Exception as e:
                    logger.warning(
                        "Failed to sync upload",
                        upload_id=str(upload.id),
                        error=str(e),
                    )

            logger.info(
                "Channel sync completed",
                channel_id=str(channel_id),
                synced_count=len(synced_ids),
            )

            return synced_ids

    async def identify_high_performers(
        self,
        channel_id: uuid.UUID,
        threshold_percentile: float | None = None,
    ) -> list[uuid.UUID]:
        """Identify high-performing videos for training data.

        High performers are videos in the top percentile by views
        and engagement rate.

        Args:
            channel_id: Database channel ID
            threshold_percentile: Percentile threshold (default from config)

        Returns:
            List of upload IDs marked as high performers
        """
        threshold = threshold_percentile or self.config.performance_percentile

        logger.info(
            "Identifying high performers",
            channel_id=str(channel_id),
            percentile=threshold,
        )

        async with self.db_session_factory() as session:
            # Get all performances for channel
            result = await session.execute(
                select(Performance)
                .join(Performance.upload)
                .join(Upload.video)
                .where(
                    Performance.views > 0,
                )
            )
            performances = result.scalars().all()

            if not performances:
                return []

            # Calculate threshold values
            views_list = sorted([p.views for p in performances])
            engagement_list = sorted([p.engagement_rate for p in performances])

            percentile_idx = int(len(views_list) * (threshold / 100))
            views_threshold = views_list[percentile_idx] if percentile_idx < len(views_list) else 0
            engagement_threshold = (
                engagement_list[percentile_idx] if percentile_idx < len(engagement_list) else 0
            )

            # Mark high performers
            high_performer_ids: list[uuid.UUID] = []
            for performance in performances:
                is_high = (
                    performance.views >= views_threshold
                    or performance.engagement_rate >= engagement_threshold
                )
                if is_high and not performance.is_high_performer:
                    performance.is_high_performer = True
                    high_performer_ids.append(performance.upload_id)

            await session.commit()

            logger.info(
                "High performers identified",
                channel_id=str(channel_id),
                count=len(high_performer_ids),
            )

            return high_performer_ids


__all__ = [
    "YouTubeAnalyticsCollector",
    "PerformanceSnapshot",
]
