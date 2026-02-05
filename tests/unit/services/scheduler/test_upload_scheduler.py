"""Unit tests for UploadScheduler service."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.youtube_upload import SchedulePreferenceConfig
from app.services.scheduler.upload_scheduler import ScheduledUpload, UploadScheduler


class TestScheduledUpload:
    """Tests for ScheduledUpload dataclass."""

    def test_basic_instantiation(self):
        """Test basic instantiation."""
        scheduled_time = datetime.now(tz=UTC)
        upload_id = uuid.uuid4()
        channel_id = uuid.uuid4()

        entry = ScheduledUpload(
            scheduled_time=scheduled_time,
            upload_id=upload_id,
            channel_id=channel_id,
        )

        assert entry.scheduled_time == scheduled_time
        assert entry.upload_id == upload_id
        assert entry.channel_id == channel_id
        assert entry.priority == 0

    def test_with_priority(self):
        """Test instantiation with priority."""
        entry = ScheduledUpload(
            scheduled_time=datetime.now(tz=UTC),
            upload_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            priority=5,
        )

        assert entry.priority == 5

    def test_ordering_by_time(self):
        """Test that entries are ordered by scheduled_time."""
        earlier = datetime.now(tz=UTC)
        later = earlier + timedelta(hours=1)

        entry1 = ScheduledUpload(
            scheduled_time=earlier,
            upload_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )
        entry2 = ScheduledUpload(
            scheduled_time=later,
            upload_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )

        assert entry1 < entry2

    def test_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        entry = ScheduledUpload(
            scheduled_time=datetime.now(tz=UTC),
            upload_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )

        assert entry.created_at is not None


class TestUploadScheduler:
    """Tests for UploadScheduler service."""

    @pytest.fixture
    def mock_db_session_factory(self):
        """Create mock database session factory."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock()
        return factory

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return SchedulePreferenceConfig(
            allowed_hours=list(range(9, 22)),
            preferred_days=None,
            min_interval_hours=4,
            max_daily_uploads=3,
        )

    @pytest.fixture
    def scheduler(self, mock_db_session_factory, config):
        """Create UploadScheduler instance."""
        return UploadScheduler(
            db_session_factory=mock_db_session_factory,
            config=config,
        )

    def test_initialization(self, scheduler):
        """Test scheduler initialization."""
        assert scheduler.config.min_interval_hours == 4
        assert scheduler.config.max_daily_uploads == 3
        assert len(scheduler._queue) == 0

    def test_get_queue_status_empty(self, scheduler):
        """Test queue status when empty."""
        status = scheduler.get_queue_status()

        assert status["total"] == 0
        assert status["pending"] == 0
        assert status["scheduled"] == 0

    def test_clear_cache(self, scheduler):
        """Test cache clearing."""
        scheduler._daily_counts[(uuid.uuid4(), "2024-01-01")] = 5
        scheduler._last_upload[uuid.uuid4()] = datetime.now(tz=UTC)

        scheduler.clear_cache()

        assert len(scheduler._daily_counts) == 0
        assert len(scheduler._last_upload) == 0


class TestUploadSchedulerTimeCalculation:
    """Tests for UploadScheduler time calculation methods."""

    @pytest.fixture
    def scheduler(self):
        """Create scheduler with specific config."""
        config = SchedulePreferenceConfig(
            allowed_hours=[10, 12, 14, 16, 18],
            preferred_days=[0, 1, 2, 3, 4],  # Weekdays
            min_interval_hours=4,
            max_daily_uploads=3,
        )
        return UploadScheduler(
            db_session_factory=MagicMock(),
            config=config,
        )

    def test_find_next_allowed_time_during_allowed_hour(self, scheduler):
        """Test finding next time when already in allowed hour."""
        # Create a time at 14:30 on a weekday
        base = datetime(2024, 1, 15, 14, 30, tzinfo=UTC)  # Monday

        result = scheduler._find_next_allowed_time(base)

        # Should return the same time since 14 is allowed
        assert result.hour == 14

    def test_find_next_allowed_time_before_first_hour(self, scheduler):
        """Test finding next time when before first allowed hour."""
        # Create a time at 8:00 (before 10:00)
        base = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)  # Monday

        result = scheduler._find_next_allowed_time(base)

        # Should return 10:00
        assert result.hour == 10
        assert result.minute == 0

    def test_find_next_allowed_time_after_last_hour(self, scheduler):
        """Test finding next time when after last allowed hour."""
        # Create a time at 20:00 (after 18:00)
        base = datetime(2024, 1, 15, 20, 0, tzinfo=UTC)  # Monday

        result = scheduler._find_next_allowed_time(base)

        # Should return next day at first allowed hour
        assert result.day == 16
        assert result.hour == 10

    def test_find_next_allowed_time_skips_weekend(self, scheduler):
        """Test finding next time skips weekend days."""
        # Create a time on Saturday
        base = datetime(2024, 1, 13, 10, 0, tzinfo=UTC)  # Saturday

        result = scheduler._find_next_allowed_time(base)

        # Should skip to Monday
        assert result.weekday() == 0  # Monday


class TestUploadSchedulerAsync:
    """Async tests for UploadScheduler."""

    @pytest.fixture
    def mock_db_session_factory(self):
        """Create mock database session factory."""
        session = AsyncMock()

        # Mock execute to return empty result for last upload query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        async def aenter(self):
            return session

        async def aexit(self, *args):
            pass

        context = MagicMock()
        context.__aenter__ = aenter
        context.__aexit__ = aexit

        factory = MagicMock(return_value=context)
        return factory

    @pytest.fixture
    def scheduler(self, mock_db_session_factory):
        """Create UploadScheduler instance."""
        config = SchedulePreferenceConfig(
            allowed_hours=list(range(9, 22)),
            min_interval_hours=4,
            max_daily_uploads=3,
        )
        return UploadScheduler(
            db_session_factory=mock_db_session_factory,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_schedule_upload_adds_to_queue(self, scheduler):
        """Test that scheduling adds entry to queue."""
        upload_id = uuid.uuid4()
        channel_id = uuid.uuid4()

        await scheduler.schedule_upload(
            upload_id=upload_id,
            channel_id=channel_id,
        )

        assert len(scheduler._queue) == 1
        assert scheduler._queue[0].upload_id == upload_id

    @pytest.mark.asyncio
    async def test_schedule_upload_respects_min_interval(self, scheduler):
        """Test that scheduling respects minimum interval."""
        channel_id = uuid.uuid4()
        upload_id1 = uuid.uuid4()
        upload_id2 = uuid.uuid4()

        # Schedule first upload
        time1 = await scheduler.schedule_upload(
            upload_id=upload_id1,
            channel_id=channel_id,
        )

        # Schedule second upload - should be at least 4 hours later
        time2 = await scheduler.schedule_upload(
            upload_id=upload_id2,
            channel_id=channel_id,
        )

        assert time2 >= time1 + timedelta(hours=4)

    @pytest.mark.asyncio
    async def test_get_pending_uploads_returns_due_entries(self, scheduler):
        """Test getting pending uploads that are due."""
        upload_id = uuid.uuid4()
        channel_id = uuid.uuid4()

        # Schedule upload in the past
        past_time = datetime.now(tz=UTC) - timedelta(hours=1)
        scheduler._queue.append(
            ScheduledUpload(
                scheduled_time=past_time,
                upload_id=upload_id,
                channel_id=channel_id,
            )
        )

        pending = await scheduler.get_pending_uploads()

        assert len(pending) == 1
        assert pending[0].upload_id == upload_id

    @pytest.mark.asyncio
    async def test_cancel_upload_removes_from_queue(self, scheduler):
        """Test that cancelling removes entry from queue."""
        upload_id = uuid.uuid4()
        channel_id = uuid.uuid4()

        # Add to queue
        scheduler._queue.append(
            ScheduledUpload(
                scheduled_time=datetime.now(tz=UTC),
                upload_id=upload_id,
                channel_id=channel_id,
            )
        )

        result = await scheduler.cancel_upload(upload_id)

        assert result is True
        assert len(scheduler._queue) == 0
