"""Unit tests for collection scheduler.

Tests the CollectionScheduler class and schedule management.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.workers.scheduler import (
    CollectionScheduler,
    ScheduleEntry,
    create_default_schedule,
    get_scheduler,
)


@pytest.fixture
def scheduler() -> CollectionScheduler:
    """Create a fresh scheduler instance."""
    return CollectionScheduler()


@pytest.fixture
def channel_id() -> str:
    """Create a test channel UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_sources() -> list[dict]:
    """Create sample source configurations."""
    return [
        {
            "type": "hackernews",
            "id": str(uuid.uuid4()),
            "config": {"limit": 30, "min_score": 50},
        },
        {
            "type": "reddit",
            "id": str(uuid.uuid4()),
            "config": {"subreddits": ["python"], "limit": 25},
        },
    ]


class TestScheduleEntry:
    """Tests for ScheduleEntry model."""

    def test_default_values(self):
        """Test ScheduleEntry default values."""
        entry = ScheduleEntry(
            name="test-schedule",
            channel_id=str(uuid.uuid4()),
            sources=[],
        )

        assert entry.cron_minute == "0"
        assert entry.cron_hour == "*/4"
        assert entry.target_language == "ko"
        assert entry.enabled is True
        assert entry.last_run is None

    def test_custom_values(self):
        """Test ScheduleEntry with custom values."""
        channel_id = str(uuid.uuid4())
        sources = [{"type": "hackernews", "id": "test", "config": {}}]

        entry = ScheduleEntry(
            name="custom-schedule",
            channel_id=channel_id,
            sources=sources,
            cron_minute="30",
            cron_hour="*/6",
            target_language="en",
            enabled=False,
        )

        assert entry.name == "custom-schedule"
        assert entry.channel_id == channel_id
        assert entry.sources == sources
        assert entry.cron_minute == "30"
        assert entry.cron_hour == "*/6"
        assert entry.target_language == "en"
        assert entry.enabled is False


class TestCollectionSchedulerAdd:
    """Tests for CollectionScheduler.add_channel_schedule()."""

    def test_add_channel_schedule_default(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test adding a schedule with default cron."""
        entry = scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
        )

        assert entry.name == f"collect-{channel_id}"
        assert entry.channel_id == channel_id
        assert entry.sources == sample_sources
        assert entry.cron_minute == "0"
        assert entry.cron_hour == "*/4"
        assert entry.enabled is True

    def test_add_channel_schedule_custom_cron(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test adding a schedule with custom cron."""
        entry = scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
            cron_minute="15",
            cron_hour="*/2",
        )

        assert entry.cron_minute == "15"
        assert entry.cron_hour == "*/2"

    def test_add_channel_schedule_stores_in_dict(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test that schedule is stored in schedules dict."""
        scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
        )

        name = f"collect-{channel_id}"
        assert name in scheduler.schedules
        assert scheduler.schedules[name].channel_id == channel_id

    def test_add_multiple_schedules(self, scheduler: CollectionScheduler, sample_sources: list):
        """Test adding multiple channel schedules."""
        channel_ids = [str(uuid.uuid4()) for _ in range(3)]

        for cid in channel_ids:
            scheduler.add_channel_schedule(channel_id=cid, sources=sample_sources)

        assert len(scheduler.schedules) == 3
        for cid in channel_ids:
            assert f"collect-{cid}" in scheduler.schedules


class TestCollectionSchedulerRemove:
    """Tests for CollectionScheduler.remove_channel_schedule()."""

    def test_remove_existing_schedule(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test removing an existing schedule."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)
        assert f"collect-{channel_id}" in scheduler.schedules

        result = scheduler.remove_channel_schedule(channel_id)

        assert result is True
        assert f"collect-{channel_id}" not in scheduler.schedules

    def test_remove_nonexistent_schedule(self, scheduler: CollectionScheduler):
        """Test removing a non-existent schedule."""
        result = scheduler.remove_channel_schedule("nonexistent-id")
        assert result is False


class TestCollectionSchedulerUpdate:
    """Tests for CollectionScheduler.update_channel_schedule()."""

    def test_update_sources(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test updating sources."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)

        new_sources = [
            {"type": "rss", "id": "new", "config": {"feed_url": "https://example.com/feed"}}
        ]
        entry = scheduler.update_channel_schedule(channel_id=channel_id, sources=new_sources)

        assert entry is not None
        assert entry.sources == new_sources

    def test_update_cron(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test updating cron expression."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)

        entry = scheduler.update_channel_schedule(
            channel_id=channel_id,
            cron_minute="30",
            cron_hour="*/8",
        )

        assert entry is not None
        assert entry.cron_minute == "30"
        assert entry.cron_hour == "*/8"

    def test_update_enabled(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test disabling a schedule."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)
        assert scheduler.schedules[f"collect-{channel_id}"].enabled is True

        entry = scheduler.update_channel_schedule(channel_id=channel_id, enabled=False)

        assert entry is not None
        assert entry.enabled is False

    def test_update_nonexistent(self, scheduler: CollectionScheduler):
        """Test updating non-existent schedule returns None."""
        result = scheduler.update_channel_schedule(
            channel_id="nonexistent",
            cron_hour="*/12",
        )
        assert result is None

    def test_partial_update(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test partial update preserves other fields."""
        scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
            target_language="en",
        )

        entry = scheduler.update_channel_schedule(channel_id=channel_id, cron_hour="*/12")

        assert entry is not None
        assert entry.target_language == "en"  # Preserved
        assert entry.sources == sample_sources  # Preserved
        assert entry.cron_hour == "*/12"  # Updated


class TestCollectionSchedulerGet:
    """Tests for CollectionScheduler.get_schedule()."""

    def test_get_existing_schedule(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test getting an existing schedule."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)

        entry = scheduler.get_schedule(channel_id)

        assert entry is not None
        assert entry.channel_id == channel_id

    def test_get_nonexistent_schedule(self, scheduler: CollectionScheduler):
        """Test getting a non-existent schedule."""
        entry = scheduler.get_schedule("nonexistent")
        assert entry is None


class TestCollectionSchedulerList:
    """Tests for CollectionScheduler.list_schedules()."""

    def test_list_empty(self, scheduler: CollectionScheduler):
        """Test listing empty schedules."""
        schedules = scheduler.list_schedules()
        assert schedules == []

    def test_list_multiple(self, scheduler: CollectionScheduler, sample_sources: list):
        """Test listing multiple schedules."""
        channel_ids = [str(uuid.uuid4()) for _ in range(3)]
        for cid in channel_ids:
            scheduler.add_channel_schedule(channel_id=cid, sources=sample_sources)

        schedules = scheduler.list_schedules()

        assert len(schedules) == 3
        listed_ids = {s.channel_id for s in schedules}
        assert listed_ids == set(channel_ids)


class TestCollectionSchedulerApply:
    """Tests for CollectionScheduler.apply_schedules()."""

    def test_apply_schedules(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test applying schedules to Celery Beat."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)

        with (
            patch.object(scheduler, "schedules", scheduler.schedules),
            patch("app.workers.scheduler.current_app") as mock_app,
        ):
            mock_app.conf = MagicMock()

            result = scheduler.apply_schedules()

            assert f"collect-{channel_id}" in result
            assert result[f"collect-{channel_id}"]["task"] == "app.workers.collect.collect_topics"

    def test_apply_skips_disabled(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test that disabled schedules are skipped."""
        scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
            enabled=False,
        )

        with patch("app.workers.scheduler.current_app") as mock_app:
            mock_app.conf = MagicMock()

            result = scheduler.apply_schedules()

            assert f"collect-{channel_id}" not in result

    def test_apply_schedule_structure(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test the structure of applied schedules."""
        scheduler.add_channel_schedule(
            channel_id=channel_id,
            sources=sample_sources,
            cron_minute="15",
            cron_hour="*/6",
            target_language="en",
        )

        with patch("app.workers.scheduler.current_app") as mock_app:
            mock_app.conf = MagicMock()

            result = scheduler.apply_schedules()

            schedule_entry = result[f"collect-{channel_id}"]
            assert schedule_entry["task"] == "app.workers.collect.collect_topics"
            assert schedule_entry["args"] == [channel_id, sample_sources, "en"]
            assert schedule_entry["options"]["queue"] == "collect"


class TestCollectionSchedulerRecordRun:
    """Tests for CollectionScheduler.record_run()."""

    def test_record_run_updates_timestamp(
        self, scheduler: CollectionScheduler, channel_id: str, sample_sources: list
    ):
        """Test recording a run updates last_run timestamp."""
        scheduler.add_channel_schedule(channel_id=channel_id, sources=sample_sources)
        assert scheduler.schedules[f"collect-{channel_id}"].last_run is None

        scheduler.record_run(channel_id)

        entry = scheduler.schedules[f"collect-{channel_id}"]
        assert entry.last_run is not None
        assert isinstance(entry.last_run, datetime)
        assert entry.last_run.tzinfo == UTC

    def test_record_run_nonexistent(self, scheduler: CollectionScheduler):
        """Test recording run for non-existent schedule does nothing."""
        # Should not raise
        scheduler.record_run("nonexistent")


class TestDefaultSchedule:
    """Tests for create_default_schedule()."""

    def test_default_schedule_structure(self):
        """Test default schedule has expected structure."""
        schedule = create_default_schedule()

        assert "health-check" in schedule
        assert schedule["health-check"]["task"] == "app.workers.collect.health_check"


class TestGetScheduler:
    """Tests for get_scheduler() singleton."""

    def test_get_scheduler_returns_instance(self):
        """Test get_scheduler returns a CollectionScheduler."""
        # Reset the global scheduler
        import app.workers.scheduler as scheduler_module

        scheduler_module._scheduler = None

        scheduler = get_scheduler()
        assert isinstance(scheduler, CollectionScheduler)

    def test_get_scheduler_singleton(self):
        """Test get_scheduler returns same instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        assert scheduler1 is scheduler2
