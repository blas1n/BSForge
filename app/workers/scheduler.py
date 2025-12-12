"""Collection scheduler for periodic topic collection.

This module manages the Celery Beat schedule for automatic topic collection
based on channel configurations.

Features:
- Dynamic schedule updates based on channel configs
- Cron-based scheduling per channel/source
- Rate limiting and backoff handling
"""

from datetime import UTC, datetime
from typing import Any

from celery import current_app
from celery.schedules import crontab
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)


class ScheduleEntry(BaseModel):
    """A scheduled collection task entry.

    Attributes:
        name: Unique task name
        channel_id: Channel UUID
        sources: Source configurations
        cron_minute: Cron minute expression
        cron_hour: Cron hour expression
        target_language: Target language for translation
        enabled: Whether the schedule is active
        last_run: Last execution timestamp
    """

    name: str
    channel_id: str
    sources: list[dict[str, Any]]
    cron_minute: str = Field(default="0")
    cron_hour: str = Field(default="*/4")  # Every 4 hours by default
    target_language: str = Field(default="ko")
    enabled: bool = Field(default=True)
    last_run: datetime | None = None


class CollectionScheduler:
    """Manages periodic collection schedules for channels.

    This scheduler integrates with Celery Beat to run collection tasks
    at configured intervals for each channel.

    Example usage:
        scheduler = CollectionScheduler()
        scheduler.add_channel_schedule(
            channel_id="uuid",
            sources=[{"type": "hackernews", "id": "uuid", "config": {}}],
            cron_hour="*/6",
        )
        scheduler.apply_schedules()
    """

    def __init__(self):
        """Initialize the scheduler."""
        self.schedules: dict[str, ScheduleEntry] = {}

    def add_channel_schedule(
        self,
        channel_id: str,
        sources: list[dict[str, Any]],
        cron_minute: str = "0",
        cron_hour: str = "*/4",
        target_language: str = "ko",
        enabled: bool = True,
    ) -> ScheduleEntry:
        """Add a collection schedule for a channel.

        Args:
            channel_id: Channel UUID
            sources: List of source configurations
            cron_minute: Cron minute expression (default: "0")
            cron_hour: Cron hour expression (default: "*/4" for every 4 hours)
            target_language: Target language for translation
            enabled: Whether the schedule is active

        Returns:
            Created ScheduleEntry
        """
        name = f"collect-{channel_id}"

        entry = ScheduleEntry(
            name=name,
            channel_id=channel_id,
            sources=sources,
            cron_minute=cron_minute,
            cron_hour=cron_hour,
            target_language=target_language,
            enabled=enabled,
        )

        self.schedules[name] = entry

        logger.info(
            f"Added schedule for channel {channel_id}",
            extra={
                "schedule_name": name,
                "cron": f"{cron_minute} {cron_hour} * * *",
                "source_count": len(sources),
            },
        )

        return entry

    def remove_channel_schedule(self, channel_id: str) -> bool:
        """Remove a channel's collection schedule.

        Args:
            channel_id: Channel UUID

        Returns:
            True if removed, False if not found
        """
        name = f"collect-{channel_id}"
        if name in self.schedules:
            del self.schedules[name]
            logger.info(f"Removed schedule for channel {channel_id}")
            return True
        return False

    def update_channel_schedule(
        self,
        channel_id: str,
        sources: list[dict[str, Any]] | None = None,
        cron_minute: str | None = None,
        cron_hour: str | None = None,
        target_language: str | None = None,
        enabled: bool | None = None,
    ) -> ScheduleEntry | None:
        """Update an existing channel schedule.

        Args:
            channel_id: Channel UUID
            sources: Optional new source configurations
            cron_minute: Optional new cron minute
            cron_hour: Optional new cron hour
            target_language: Optional new target language
            enabled: Optional enable/disable

        Returns:
            Updated ScheduleEntry or None if not found
        """
        name = f"collect-{channel_id}"
        if name not in self.schedules:
            logger.warning(f"Schedule not found for channel {channel_id}")
            return None

        entry = self.schedules[name]

        if sources is not None:
            entry.sources = sources
        if cron_minute is not None:
            entry.cron_minute = cron_minute
        if cron_hour is not None:
            entry.cron_hour = cron_hour
        if target_language is not None:
            entry.target_language = target_language
        if enabled is not None:
            entry.enabled = enabled

        logger.info(f"Updated schedule for channel {channel_id}")
        return entry

    def get_schedule(self, channel_id: str) -> ScheduleEntry | None:
        """Get schedule entry for a channel.

        Args:
            channel_id: Channel UUID

        Returns:
            ScheduleEntry or None if not found
        """
        name = f"collect-{channel_id}"
        return self.schedules.get(name)

    def list_schedules(self) -> list[ScheduleEntry]:
        """List all registered schedules.

        Returns:
            List of all ScheduleEntry objects
        """
        return list(self.schedules.values())

    def apply_schedules(self) -> dict[str, Any]:
        """Apply all schedules to Celery Beat.

        This updates the Celery Beat schedule with all configured
        channel collection tasks.

        Returns:
            Dict of applied beat schedules
        """
        beat_schedule: dict[str, Any] = {}

        for name, entry in self.schedules.items():
            if not entry.enabled:
                logger.debug(f"Skipping disabled schedule: {name}")
                continue

            beat_schedule[name] = {
                "task": "app.workers.collect.collect_topics",
                "schedule": crontab(
                    minute=entry.cron_minute,
                    hour=entry.cron_hour,
                ),
                "args": [
                    entry.channel_id,
                    entry.sources,
                    entry.target_language,
                ],
                "options": {
                    "queue": "collect",
                },
            }

        # Update Celery beat schedule
        current_app.conf.beat_schedule = beat_schedule

        logger.info(
            f"Applied {len(beat_schedule)} schedules to Celery Beat",
            extra={"schedule_names": list(beat_schedule.keys())},
        )

        return beat_schedule

    def record_run(self, channel_id: str) -> None:
        """Record that a collection task has run.

        Args:
            channel_id: Channel UUID
        """
        name = f"collect-{channel_id}"
        if name in self.schedules:
            self.schedules[name].last_run = datetime.now(UTC)


def create_default_schedule() -> dict[str, Any]:
    """Create default Celery Beat schedule configuration.

    This is used when no dynamic schedules are configured.
    Includes maintenance tasks and health checks.

    Returns:
        Default beat schedule dict
    """
    return {
        # Health check every 5 minutes
        "health-check": {
            "task": "app.workers.collect.health_check",
            "schedule": crontab(minute="*/5"),
            "options": {"queue": "default"},
        },
    }


# Global scheduler instance
_scheduler: CollectionScheduler | None = None


def get_scheduler() -> CollectionScheduler:
    """Get or create the global scheduler instance.

    Returns:
        CollectionScheduler singleton
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = CollectionScheduler()
    return _scheduler


__all__ = [
    "CollectionScheduler",
    "ScheduleEntry",
    "create_default_schedule",
    "get_scheduler",
]
