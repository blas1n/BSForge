"""Unit tests for Series model structure."""

import pytest

from app.models.series import Series, SeriesStatus


class TestSeriesStatus:
    """Tests for SeriesStatus enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert SeriesStatus.ACTIVE.value == "active"
        assert SeriesStatus.PAUSED.value == "paused"
        assert SeriesStatus.ENDED.value == "ended"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert SeriesStatus("active") == SeriesStatus.ACTIVE
        assert SeriesStatus("paused") == SeriesStatus.PAUSED
        assert SeriesStatus("ended") == SeriesStatus.ENDED

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            SeriesStatus("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(SeriesStatus.ACTIVE, str)
        assert SeriesStatus.ACTIVE == "active"

    def test_all_statuses_count(self):
        """Test that all expected statuses exist."""
        all_statuses = list(SeriesStatus)
        assert len(all_statuses) == 3


class TestSeriesModel:
    """Tests for Series model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert Series.__tablename__ == "series"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = Series.__table__.columns
        required_columns = [
            "id",
            "channel_id",
            "name",
            "description",
            "criteria_keywords",
            "criteria_categories",
            "min_similarity",
            "episode_count",
            "avg_views",
            "avg_engagement",
            "trend",
            "status",
            "auto_detected",
            "confirmed_by_user",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = Series.__table__.columns

        # channel_id FK
        channel_fks = list(columns["channel_id"].foreign_keys)
        assert len(channel_fks) == 1
        assert "channels.id" in str(channel_fks[0])

    def test_channel_id_not_nullable(self):
        """Test that channel_id is not nullable."""
        columns = Series.__table__.columns
        assert columns["channel_id"].nullable is False

    def test_name_not_nullable(self):
        """Test that name is not nullable."""
        columns = Series.__table__.columns
        assert columns["name"].nullable is False

    def test_optional_fields_are_nullable(self):
        """Test that optional fields are nullable."""
        columns = Series.__table__.columns
        assert columns["description"].nullable is True
        assert columns["criteria_keywords"].nullable is True
        assert columns["criteria_categories"].nullable is True

    def test_default_min_similarity(self):
        """Test default min_similarity is 0.6."""
        columns = Series.__table__.columns
        min_similarity_col = columns["min_similarity"]
        assert min_similarity_col.default.arg == 0.6

    def test_default_episode_count(self):
        """Test default episode_count is 0."""
        columns = Series.__table__.columns
        episode_count_col = columns["episode_count"]
        assert episode_count_col.default.arg == 0

    def test_default_avg_views(self):
        """Test default avg_views is 0.0."""
        columns = Series.__table__.columns
        avg_views_col = columns["avg_views"]
        assert avg_views_col.default.arg == 0.0

    def test_default_avg_engagement(self):
        """Test default avg_engagement is 0.0."""
        columns = Series.__table__.columns
        avg_engagement_col = columns["avg_engagement"]
        assert avg_engagement_col.default.arg == 0.0

    def test_default_trend(self):
        """Test default trend is 'stable'."""
        columns = Series.__table__.columns
        trend_col = columns["trend"]
        assert trend_col.default.arg == "stable"

    def test_default_status(self):
        """Test default status is ACTIVE."""
        columns = Series.__table__.columns
        status_col = columns["status"]
        assert status_col.default.arg == SeriesStatus.ACTIVE

    def test_default_auto_detected(self):
        """Test default auto_detected is True."""
        columns = Series.__table__.columns
        auto_detected_col = columns["auto_detected"]
        assert auto_detected_col.default.arg is True

    def test_default_confirmed_by_user(self):
        """Test default confirmed_by_user is False."""
        columns = Series.__table__.columns
        confirmed_col = columns["confirmed_by_user"]
        assert confirmed_col.default.arg is False

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = Series.__table__.indexes
        index_names = [idx.name for idx in indexes]

        assert "idx_series_channel" in index_names
        assert "idx_series_status" in index_names
        assert "idx_series_channel_status" in index_names

    def test_repr(self):
        """Test string representation."""
        series = Series()
        series.id = "test-id"
        series.name = "Tech News Series"
        series.episode_count = 10
        series.status = SeriesStatus.ACTIVE

        repr_str = repr(series)
        assert "Series" in repr_str
        assert "test-id" in repr_str
        assert "Tech News Series" in repr_str
        assert "10" in repr_str


class TestSeriesProperties:
    """Tests for Series model properties."""

    def test_is_active_when_active(self):
        """Test is_active property when status is ACTIVE."""
        series = Series()
        series.status = SeriesStatus.ACTIVE
        assert series.is_active is True

    def test_is_active_when_paused(self):
        """Test is_active property when status is PAUSED."""
        series = Series()
        series.status = SeriesStatus.PAUSED
        assert series.is_active is False

    def test_is_active_when_ended(self):
        """Test is_active property when status is ENDED."""
        series = Series()
        series.status = SeriesStatus.ENDED
        assert series.is_active is False


class TestSeriesLifecycle:
    """Tests for Series status lifecycle."""

    def test_initial_status_is_active(self):
        """Test that series start in ACTIVE status."""
        columns = Series.__table__.columns
        status_col = columns["status"]
        assert status_col.default.arg == SeriesStatus.ACTIVE

    def test_status_can_be_paused(self):
        """Test that PAUSED status exists."""
        assert SeriesStatus.PAUSED in SeriesStatus
        assert SeriesStatus.PAUSED.value == "paused"

    def test_status_can_be_ended(self):
        """Test that ENDED status exists."""
        assert SeriesStatus.ENDED in SeriesStatus
        assert SeriesStatus.ENDED.value == "ended"
