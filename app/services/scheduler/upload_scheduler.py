"""Upload scheduler service.

This module provides the UploadScheduler for scheduling YouTube uploads
with constraint-based optimal timing using a priority queue.
"""

import heapq
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config.youtube_upload import SchedulePreferenceConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.upload import Upload, UploadStatus
from app.services.analytics.optimal_time import OptimalTimeAnalyzer, TimeSlotAnalysis

logger = get_logger(__name__)


@dataclass(order=True)
class ScheduledUpload:
    """Scheduled upload entry for priority queue.

    Attributes:
        scheduled_time: When to upload (used for ordering)
        upload_id: Database upload ID
        channel_id: Channel ID for constraint tracking
        priority: Upload priority (lower = higher priority)
        created_at: When the schedule was created
    """

    scheduled_time: datetime
    upload_id: uuid.UUID = field(compare=False)
    channel_id: uuid.UUID = field(compare=False)
    priority: int = field(default=0, compare=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC), compare=False)


class UploadScheduler:
    """Scheduler for YouTube uploads with constraints.

    Manages upload scheduling with:
    - Minimum interval between uploads (default 4 hours)
    - Maximum daily uploads per channel (default 3)
    - Optimal time analysis integration
    - Priority-based scheduling

    Example:
        >>> scheduler = UploadScheduler(db_session_factory, config)
        >>> scheduled_time = await scheduler.schedule_upload(
        ...     upload_id=upload.id,
        ...     channel_id=channel.id,
        ... )
        >>> print(f"Scheduled for: {scheduled_time}")
    """

    def __init__(
        self,
        db_session_factory: SessionFactory,
        config: SchedulePreferenceConfig | None = None,
        optimal_time_analyzer: OptimalTimeAnalyzer | None = None,
    ) -> None:
        """Initialize upload scheduler.

        Args:
            db_session_factory: Database session factory
            config: Schedule preference configuration
            optimal_time_analyzer: Optional analyzer for optimal times
        """
        self.db_session_factory = db_session_factory
        self.config = config or SchedulePreferenceConfig()
        self.optimal_time_analyzer = optimal_time_analyzer

        # In-memory priority queue for pending uploads
        self._queue: list[ScheduledUpload] = []

        # Track uploads per channel per day
        self._daily_counts: dict[tuple[uuid.UUID, str], int] = {}

        # Track last upload time per channel
        self._last_upload: dict[uuid.UUID, datetime] = {}

        logger.info(
            "UploadScheduler initialized",
            min_interval_hours=self.config.min_interval_hours,
            max_daily_uploads=self.config.max_daily_uploads,
        )

    async def schedule_upload(
        self,
        upload_id: uuid.UUID,
        channel_id: uuid.UUID,
        preferred_time: datetime | None = None,
        priority: int = 0,
        analysis: TimeSlotAnalysis | None = None,
    ) -> datetime:
        """Schedule an upload with constraint checking.

        Finds the next available time slot considering:
        - Minimum interval constraint
        - Daily upload limit
        - Allowed hours
        - Optimal time analysis (if available)

        Args:
            upload_id: Database upload ID
            channel_id: Channel ID
            preferred_time: Preferred upload time (optional)
            priority: Upload priority (lower = higher)
            analysis: Optional time slot analysis

        Returns:
            Scheduled datetime
        """
        now = datetime.now(tz=UTC)
        base_time = preferred_time or now

        # Get constraints for this channel
        last_upload = await self._get_last_upload_time(channel_id)
        daily_count = await self._get_daily_upload_count(channel_id, base_time)

        # Calculate earliest possible time
        earliest = now
        if last_upload:
            min_interval = timedelta(hours=self.config.min_interval_hours)
            interval_earliest = last_upload + min_interval
            earliest = max(earliest, interval_earliest)

        # If daily limit reached, push to next day
        if daily_count >= self.config.max_daily_uploads:
            next_day = base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            earliest = max(earliest, next_day)
            logger.info(
                "Daily limit reached, scheduling for next day",
                channel_id=str(channel_id),
                next_day=next_day.isoformat(),
            )

        # Find optimal time within constraints
        if analysis and self.optimal_time_analyzer:
            scheduled_time = self.optimal_time_analyzer.get_next_optimal_time(
                analysis=analysis,
                after=earliest,
                allowed_hours=self.config.allowed_hours,
                preferred_days=self.config.preferred_days,
            )
        else:
            scheduled_time = self._find_next_allowed_time(earliest)

        # Create scheduled entry
        entry = ScheduledUpload(
            scheduled_time=scheduled_time,
            upload_id=upload_id,
            channel_id=channel_id,
            priority=priority,
        )
        heapq.heappush(self._queue, entry)

        # Update tracking
        self._last_upload[channel_id] = scheduled_time
        day_key = (channel_id, scheduled_time.strftime("%Y-%m-%d"))
        self._daily_counts[day_key] = self._daily_counts.get(day_key, 0) + 1

        # Persist to database
        await self._update_upload_schedule(upload_id, scheduled_time)

        logger.info(
            "Upload scheduled",
            upload_id=str(upload_id),
            channel_id=str(channel_id),
            scheduled_time=scheduled_time.isoformat(),
            priority=priority,
        )

        return scheduled_time

    def _find_next_allowed_time(self, after: datetime) -> datetime:
        """Find next allowed time slot.

        Args:
            after: Earliest allowed time

        Returns:
            Next allowed datetime
        """
        candidate = after

        # Check if current hour is allowed
        if candidate.hour not in self.config.allowed_hours:
            # Find next allowed hour
            for hour in sorted(self.config.allowed_hours):
                if hour > candidate.hour:
                    candidate = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
                    break
            else:
                # No allowed hour today, go to next day
                candidate = candidate.replace(
                    hour=self.config.allowed_hours[0],
                    minute=0,
                    second=0,
                    microsecond=0,
                ) + timedelta(days=1)

        # Check preferred days
        if self.config.preferred_days:
            max_days = 7
            days_checked = 0
            while candidate.weekday() not in self.config.preferred_days and days_checked < max_days:
                candidate = candidate + timedelta(days=1)
                candidate = candidate.replace(
                    hour=self.config.allowed_hours[0],
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                days_checked += 1

        return candidate

    async def _get_last_upload_time(self, channel_id: uuid.UUID) -> datetime | None:
        """Get last upload time for channel.

        Args:
            channel_id: Channel ID

        Returns:
            Last upload datetime or None
        """
        # Check in-memory cache first
        if channel_id in self._last_upload:
            return self._last_upload[channel_id]

        # Query database
        async with self.db_session_factory() as session:
            result = await session.execute(
                select(Upload.uploaded_at)
                .join(Upload.video)
                .where(
                    Upload.upload_status == UploadStatus.COMPLETED,
                    Upload.uploaded_at.isnot(None),
                )
                .order_by(Upload.uploaded_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()

            if row:
                self._last_upload[channel_id] = row
            return row

    async def _get_daily_upload_count(self, channel_id: uuid.UUID, date: datetime) -> int:
        """Get upload count for channel on given date.

        Args:
            channel_id: Channel ID
            date: Date to check

        Returns:
            Number of uploads scheduled/completed
        """
        day_key = (channel_id, date.strftime("%Y-%m-%d"))

        # Check in-memory cache first
        if day_key in self._daily_counts:
            return self._daily_counts[day_key]

        # Query database
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        async with self.db_session_factory() as session:
            result = await session.execute(
                select(Upload)
                .join(Upload.video)
                .where(
                    Upload.upload_status.in_([UploadStatus.SCHEDULED, UploadStatus.COMPLETED]),
                    Upload.scheduled_at >= day_start,
                    Upload.scheduled_at < day_end,
                )
            )
            count = len(result.all())
            self._daily_counts[day_key] = count
            return count

    async def _update_upload_schedule(self, upload_id: uuid.UUID, scheduled_time: datetime) -> None:
        """Update upload record with scheduled time.

        Args:
            upload_id: Upload ID
            scheduled_time: Scheduled datetime
        """
        async with self.db_session_factory() as session:
            result = await session.execute(select(Upload).where(Upload.id == upload_id))
            upload = result.scalar_one_or_none()

            if upload:
                upload.scheduled_at = scheduled_time
                upload.upload_status = UploadStatus.SCHEDULED
                await session.commit()

    async def get_pending_uploads(
        self, before: datetime | None = None, limit: int = 10
    ) -> list[ScheduledUpload]:
        """Get pending uploads ready for processing.

        Args:
            before: Only uploads scheduled before this time
            limit: Maximum number to return

        Returns:
            List of scheduled uploads
        """
        before = before or datetime.now(tz=UTC)
        result = []

        # Get from in-memory queue
        while self._queue and len(result) < limit:
            entry = self._queue[0]
            if entry.scheduled_time <= before:
                result.append(heapq.heappop(self._queue))
            else:
                break

        # Also check database for any missed scheduled uploads
        async with self.db_session_factory() as session:
            db_result = await session.execute(
                select(Upload)
                .where(
                    Upload.upload_status == UploadStatus.SCHEDULED,
                    Upload.scheduled_at <= before,
                )
                .order_by(Upload.scheduled_at)
                .limit(limit - len(result))
            )
            uploads = db_result.scalars().all()

            for upload in uploads:
                # Avoid duplicates
                if not any(e.upload_id == upload.id for e in result):
                    entry = ScheduledUpload(
                        scheduled_time=upload.scheduled_at or datetime.now(tz=UTC),
                        upload_id=upload.id,
                        channel_id=upload.video.channel_id,
                    )
                    result.append(entry)

        return result

    async def reschedule_upload(
        self,
        upload_id: uuid.UUID,
        new_time: datetime | None = None,
        reason: str = "manual",
    ) -> datetime:
        """Reschedule an upload to a new time.

        Args:
            upload_id: Upload ID to reschedule
            new_time: New scheduled time (or auto-calculate)
            reason: Reason for rescheduling

        Returns:
            New scheduled datetime
        """
        # Remove from queue if present
        self._queue = [e for e in self._queue if e.upload_id != upload_id]
        heapq.heapify(self._queue)

        # Get upload info
        async with self.db_session_factory() as session:
            result = await session.execute(select(Upload).where(Upload.id == upload_id))
            upload = result.scalar_one_or_none()

            if not upload:
                raise ValueError(f"Upload not found: {upload_id}")

            channel_id = upload.video.channel_id

        # Schedule with new time
        scheduled = await self.schedule_upload(
            upload_id=upload_id,
            channel_id=channel_id,
            preferred_time=new_time,
        )

        logger.info(
            "Upload rescheduled",
            upload_id=str(upload_id),
            new_time=scheduled.isoformat(),
            reason=reason,
        )

        return scheduled

    async def cancel_upload(self, upload_id: uuid.UUID, reason: str = "manual") -> bool:
        """Cancel a scheduled upload.

        Args:
            upload_id: Upload ID to cancel
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        # Remove from queue
        original_len = len(self._queue)
        self._queue = [e for e in self._queue if e.upload_id != upload_id]
        heapq.heapify(self._queue)
        removed = len(self._queue) < original_len

        # Update database
        async with self.db_session_factory() as session:
            result = await session.execute(select(Upload).where(Upload.id == upload_id))
            upload = result.scalar_one_or_none()

            if upload and upload.upload_status == UploadStatus.SCHEDULED:
                upload.upload_status = UploadStatus.PENDING
                upload.scheduled_at = None
                await session.commit()
                removed = True

        if removed:
            logger.info(
                "Upload cancelled",
                upload_id=str(upload_id),
                reason=reason,
            )

        return removed

    def get_queue_status(self) -> dict[str, int]:
        """Get current queue status.

        Returns:
            Dictionary with queue statistics
        """
        now = datetime.now(tz=UTC)
        pending = sum(1 for e in self._queue if e.scheduled_time <= now)
        scheduled = len(self._queue) - pending

        return {
            "total": len(self._queue),
            "pending": pending,
            "scheduled": scheduled,
        }

    def clear_cache(self) -> None:
        """Clear in-memory caches.

        Call this when external changes may have affected scheduling.
        """
        self._daily_counts.clear()
        self._last_upload.clear()
        logger.debug("Scheduler cache cleared")


__all__ = [
    "ScheduledUpload",
    "UploadScheduler",
]
