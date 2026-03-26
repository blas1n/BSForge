"""Unit tests for OptimalTimeAnalyzer service."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.youtube_upload import AnalyticsConfig
from app.models.performance import Performance
from app.models.upload import Upload
from app.services.analytics.optimal_time import (
    KOREAN_GOLDEN_HOURS,
    OptimalTimeAnalyzer,
    TimeSlot,
    TimeSlotAnalysis,
)
from tests.conftest import make_mock_session_factory


class TestTimeSlot:
    """Tests for TimeSlot dataclass."""

    def test_default_values(self):
        """Test default instantiation."""
        slot = TimeSlot(hour=14)

        assert slot.hour == 14
        assert slot.day_of_week is None
        assert slot.avg_views == 0.0
        assert slot.avg_engagement == 0.0
        assert slot.sample_count == 0
        assert slot.score == 0.0

    def test_with_all_fields(self):
        """Test full instantiation."""
        slot = TimeSlot(
            hour=18,
            day_of_week=2,
            avg_views=500.0,
            avg_engagement=0.05,
            sample_count=10,
            score=0.85,
        )

        assert slot.hour == 18
        assert slot.day_of_week == 2
        assert slot.score == 0.85


class TestTimeSlotAnalysis:
    """Tests for TimeSlotAnalysis dataclass."""

    def test_default_values(self):
        """Test default instantiation."""
        analysis = TimeSlotAnalysis()

        assert analysis.best_hours == []
        assert analysis.best_days == []
        assert analysis.best_slots == []
        assert analysis.worst_slots == []
        assert analysis.confidence_scores == {}
        assert analysis.sample_size == 0
        assert analysis.analysis_period_days == 90

    def test_with_data(self):
        """Test instantiation with data."""
        analysis = TimeSlotAnalysis(
            best_hours=[18, 12, 21],
            best_days=[5, 6],
            sample_size=50,
        )

        assert analysis.best_hours == [18, 12, 21]
        assert analysis.sample_size == 50


class TestOptimalTimeAnalyzer:
    """Tests for OptimalTimeAnalyzer service."""

    @pytest.fixture
    def mock_db_session_and_factory(self):
        """Create mock database session and factory."""
        return make_mock_session_factory()

    @pytest.fixture
    def mock_db_session_factory(self, mock_db_session_and_factory):
        """Get mock factory."""
        return mock_db_session_and_factory[0]

    @pytest.fixture
    def mock_db_session(self, mock_db_session_and_factory):
        """Get mock session."""
        return mock_db_session_and_factory[1]

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AnalyticsConfig(
            min_sample_size=5,
            metrics_lookback_days=90,
            engagement_weight=0.4,
        )

    @pytest.fixture
    def analyzer(self, mock_db_session_factory, config):
        """Create OptimalTimeAnalyzer instance."""
        return OptimalTimeAnalyzer(
            db_session_factory=mock_db_session_factory,
            config=config,
        )

    # =========================================================================
    # Initialization tests
    # =========================================================================

    def test_default_config(self):
        """Test initialization with default config."""
        analyzer = OptimalTimeAnalyzer(db_session_factory=MagicMock())

        assert analyzer.config is not None
        assert analyzer.config.min_sample_size == 10

    def test_custom_config(self, config):
        """Test initialization with custom config."""
        analyzer = OptimalTimeAnalyzer(
            db_session_factory=MagicMock(),
            config=config,
        )

        assert analyzer.config.min_sample_size == 5

    # =========================================================================
    # analyze_channel() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data_returns_defaults(self, analyzer, mock_db_session):
        """Test default analysis when insufficient data."""
        # Return fewer rows than min_sample_size (5)
        mock_result = MagicMock()
        mock_result.all.return_value = [(MagicMock(), MagicMock())] * 3
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        analysis = await analyzer.analyze_channel(uuid.uuid4())

        assert analysis.best_hours == KOREAN_GOLDEN_HOURS["weekday"]
        assert analysis.best_days == [5, 6]
        assert analysis.sample_size == 3

    @pytest.mark.asyncio
    async def test_analyze_with_sufficient_data(self, analyzer, mock_db_session):
        """Test analysis with enough data points."""
        rows = []
        for i in range(10):
            upload = MagicMock(spec=Upload)
            upload.uploaded_at = datetime(2024, 1, 15 + (i % 5), 10 + i, 0, tzinfo=UTC)

            perf = MagicMock(spec=Performance)
            perf.views = 100 + i * 50
            perf.engagement_rate = 0.03 + i * 0.005

            rows.append((upload, perf))

        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        analysis = await analyzer.analyze_channel(uuid.uuid4())

        assert analysis.sample_size == 10
        assert len(analysis.best_hours) > 0
        assert len(analysis.best_slots) > 0
        assert analysis.analysis_period_days == 90

    @pytest.mark.asyncio
    async def test_analyze_custom_lookback(self, analyzer, mock_db_session):
        """Test analysis with custom lookback days."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        analysis = await analyzer.analyze_channel(uuid.uuid4(), days_lookback=30)

        assert analysis.analysis_period_days == 30

    @pytest.mark.asyncio
    async def test_analyze_skips_null_uploaded_at(self, analyzer, mock_db_session):
        """Test that rows with null uploaded_at are skipped."""
        rows = []
        # 5 valid rows + 1 null
        for i in range(5):
            upload = MagicMock(spec=Upload)
            upload.uploaded_at = datetime(2024, 1, 15, 10 + i, 0, tzinfo=UTC)
            perf = MagicMock(spec=Performance)
            perf.views = 100
            perf.engagement_rate = 0.05
            rows.append((upload, perf))

        # Add one with null uploaded_at
        null_upload = MagicMock(spec=Upload)
        null_upload.uploaded_at = None
        null_perf = MagicMock(spec=Performance)
        null_perf.views = 9999
        null_perf.engagement_rate = 0.99
        rows.append((null_upload, null_perf))

        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        analysis = await analyzer.analyze_channel(uuid.uuid4())

        # Should have 5 valid data points (+ 1 null skipped)
        assert analysis.sample_size == 6  # Total rows counted

    # =========================================================================
    # _calculate_scores() tests
    # =========================================================================

    def test_calculate_scores_single_hour(self, analyzer):
        """Test score calculation with single hour data."""
        hour_data = {14: [(1000.0, 0.05), (800.0, 0.04)]}
        day_data = {0: [(1000.0, 0.05), (800.0, 0.04)]}
        slot_data = {(14, 0): [(1000.0, 0.05), (800.0, 0.04)]}

        analysis = analyzer._calculate_scores(hour_data, day_data, slot_data, 2, 30)

        assert len(analysis.best_hours) == 1
        assert analysis.best_hours[0] == 14
        assert analysis.sample_size == 2

    def test_calculate_scores_multiple_hours(self, analyzer):
        """Test score calculation ranks hours by performance."""
        hour_data = {
            10: [(200.0, 0.02)],
            14: [(1000.0, 0.08)],
            18: [(800.0, 0.06)],
        }
        day_data = {0: [(200.0, 0.02), (1000.0, 0.08), (800.0, 0.06)]}
        slot_data = {
            (10, 0): [(200.0, 0.02)],
            (14, 0): [(1000.0, 0.08)],
            (18, 0): [(800.0, 0.06)],
        }

        analysis = analyzer._calculate_scores(hour_data, day_data, slot_data, 3, 30)

        # Best hour should be 14 (highest views and engagement)
        assert analysis.best_hours[0] == 14

    def test_calculate_scores_confidence_by_sample(self, analyzer):
        """Test that confidence increases with sample count."""
        # One hour with many samples
        hour_data_many = {14: [(500.0, 0.05)] * 20}
        # One hour with few samples
        hour_data_few = {18: [(500.0, 0.05)] * 2}

        combined_hour = {**hour_data_many, **hour_data_few}
        day_data = {0: [(500.0, 0.05)] * 22}
        slot_data = {}

        analysis = analyzer._calculate_scores(combined_hour, day_data, slot_data, 22, 30)

        assert analysis.confidence_scores["hour_14"] == 1.0  # 20/10 capped at 1.0
        assert analysis.confidence_scores["hour_18"] == pytest.approx(0.2)  # 2/10

    def test_calculate_scores_worst_slots(self, analyzer):
        """Test that worst slots are returned."""
        # Create 6+ slots for worst_slots to be populated
        hour_data = {}
        day_data = {}
        slot_data = {}
        for h in range(6):
            hour_data[h + 10] = [(100.0 * (h + 1), 0.01 * (h + 1))]
            day_data[h % 5] = day_data.get(h % 5, []) + [(100.0 * (h + 1), 0.01 * (h + 1))]
            slot_data[(h + 10, h % 5)] = [(100.0 * (h + 1), 0.01 * (h + 1))]

        analysis = analyzer._calculate_scores(hour_data, day_data, slot_data, 6, 30)

        assert len(analysis.worst_slots) > 0

    def test_calculate_scores_few_slots_no_worst(self, analyzer):
        """Test that worst slots are empty when < 5 combined slots."""
        hour_data = {14: [(500.0, 0.05)]}
        day_data = {0: [(500.0, 0.05)]}
        slot_data = {(14, 0): [(500.0, 0.05)]}

        analysis = analyzer._calculate_scores(hour_data, day_data, slot_data, 1, 30)

        assert analysis.worst_slots == []

    # =========================================================================
    # _get_default_analysis() tests
    # =========================================================================

    def test_default_analysis_uses_korean_golden_hours(self, analyzer):
        """Test default analysis uses Korean golden hours."""
        analysis = analyzer._get_default_analysis(3, 90)

        assert analysis.best_hours == KOREAN_GOLDEN_HOURS["weekday"]
        assert analysis.best_days == [5, 6]
        assert analysis.sample_size == 3
        assert analysis.analysis_period_days == 90
        assert analysis.confidence_scores == {"default": 0.5}

    def test_default_analysis_has_best_slots(self, analyzer):
        """Test default analysis creates slots for golden hours."""
        analysis = analyzer._get_default_analysis(0, 30)

        assert len(analysis.best_slots) == len(KOREAN_GOLDEN_HOURS["weekday"])
        for slot in analysis.best_slots:
            assert slot.score == 0.8

    # =========================================================================
    # get_next_optimal_time() tests
    # =========================================================================

    def test_next_optimal_time_basic(self, analyzer):
        """Test basic next optimal time calculation."""
        analysis = TimeSlotAnalysis(
            best_hours=[14, 18, 21],
            best_days=[0, 1, 2, 3, 4],
        )

        # Monday at 10:00
        after = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(analysis, after=after)

        assert result.hour == 14
        assert result > after

    def test_next_optimal_time_after_all_best_hours(self, analyzer):
        """Test next time when past all best hours today."""
        analysis = TimeSlotAnalysis(
            best_hours=[10, 14],
        )

        # Already past 14:00
        after = datetime(2024, 1, 15, 15, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(analysis, after=after)

        # Should go to next day at 10
        assert result.day == 16
        assert result.hour == 10

    def test_next_optimal_time_respects_allowed_hours(self, analyzer):
        """Test that allowed_hours filter is applied."""
        analysis = TimeSlotAnalysis(
            best_hours=[6, 10, 22],  # 6 and 22 outside allowed
        )

        after = datetime(2024, 1, 15, 5, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(
            analysis,
            after=after,
            allowed_hours=list(range(9, 18)),
        )

        assert 9 <= result.hour < 18

    def test_next_optimal_time_respects_preferred_days(self, analyzer):
        """Test that preferred_days filter is applied."""
        analysis = TimeSlotAnalysis(
            best_hours=[10, 14],
        )

        # Saturday
        after = datetime(2024, 1, 13, 8, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(
            analysis,
            after=after,
            preferred_days=[0, 1, 2, 3, 4],  # Weekdays only
        )

        # Should skip to Monday
        assert result.weekday() in [0, 1, 2, 3, 4]

    def test_next_optimal_time_fallback(self, analyzer):
        """Test fallback when no optimal slot found in 7 days."""
        analysis = TimeSlotAnalysis(
            best_hours=[],  # No best hours
        )

        after = datetime(2024, 1, 15, 20, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(
            analysis,
            after=after,
            allowed_hours=[10, 14, 18],
        )

        # Should fallback to next day at first allowed hour
        assert result > after

    def test_next_optimal_time_defaults(self, analyzer):
        """Test with default parameters."""
        analysis = TimeSlotAnalysis(
            best_hours=[14],
        )

        result = analyzer.get_next_optimal_time(analysis)

        # Should return a future time
        assert result > datetime.now(tz=UTC) - timedelta(seconds=1)

    def test_next_optimal_time_no_best_hours_uses_allowed(self, analyzer):
        """Test that allowed_hours are used when best_hours not in allowed."""
        analysis = TimeSlotAnalysis(
            best_hours=[3, 4, 5],  # All outside default allowed
        )

        after = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)

        result = analyzer.get_next_optimal_time(
            analysis,
            after=after,
            allowed_hours=[10, 14, 18],
        )

        assert result.hour in [10, 14, 18]
