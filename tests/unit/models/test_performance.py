"""Unit tests for Performance model structure."""

from app.models.performance import Performance


class TestPerformanceModel:
    """Tests for Performance model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert Performance.__tablename__ == "performances"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = Performance.__table__.columns
        required_columns = [
            "id",
            "upload_id",
            "views",
            "likes",
            "dislikes",
            "comments",
            "shares",
            "watch_time_seconds",
            "avg_view_duration",
            "avg_view_percentage",
            "engagement_rate",
            "ctr",
            "subscribers_gained",
            "subscribers_lost",
            "traffic_sources",
            "demographics",
            "daily_snapshots",
            "last_synced_at",
            "is_high_performer",
            "added_to_training",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = Performance.__table__.columns

        # upload_id FK
        upload_fks = list(columns["upload_id"].foreign_keys)
        assert len(upload_fks) == 1
        assert "uploads.id" in str(upload_fks[0])

    def test_upload_id_is_unique(self):
        """Test that upload_id is unique."""
        columns = Performance.__table__.columns
        assert columns["upload_id"].unique is True

    def test_upload_id_not_nullable(self):
        """Test that upload_id is not nullable."""
        columns = Performance.__table__.columns
        assert columns["upload_id"].nullable is False

    def test_metrics_not_nullable(self):
        """Test that metric fields are not nullable."""
        columns = Performance.__table__.columns
        assert columns["views"].nullable is False
        assert columns["likes"].nullable is False
        assert columns["dislikes"].nullable is False
        assert columns["comments"].nullable is False
        assert columns["shares"].nullable is False

    def test_jsonb_fields_nullable(self):
        """Test that JSONB fields are nullable."""
        columns = Performance.__table__.columns
        assert columns["traffic_sources"].nullable is True
        assert columns["demographics"].nullable is True
        assert columns["daily_snapshots"].nullable is True

    def test_default_metrics_zero(self):
        """Test default metric values are zero."""
        columns = Performance.__table__.columns
        assert columns["views"].default.arg == 0
        assert columns["likes"].default.arg == 0
        assert columns["dislikes"].default.arg == 0
        assert columns["comments"].default.arg == 0
        assert columns["shares"].default.arg == 0
        assert columns["watch_time_seconds"].default.arg == 0
        assert columns["subscribers_gained"].default.arg == 0
        assert columns["subscribers_lost"].default.arg == 0

    def test_default_rates_zero(self):
        """Test default rate values are zero."""
        columns = Performance.__table__.columns
        assert columns["avg_view_duration"].default.arg == 0.0
        assert columns["avg_view_percentage"].default.arg == 0.0
        assert columns["engagement_rate"].default.arg == 0.0
        assert columns["ctr"].default.arg == 0.0

    def test_default_flags_false(self):
        """Test default boolean flags are False."""
        columns = Performance.__table__.columns
        assert columns["is_high_performer"].default.arg is False
        assert columns["added_to_training"].default.arg is False

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = Performance.__table__.indexes
        index_names = [idx.name for idx in indexes]

        assert "idx_performance_high" in index_names
        assert "idx_performance_views" in index_names

    def test_repr(self):
        """Test string representation."""
        performance = Performance()
        performance.id = "test-id"
        performance.upload_id = "upload-123"
        performance.views = 1000
        performance.engagement_rate = 0.05

        repr_str = repr(performance)
        assert "Performance" in repr_str
        assert "test-id" in repr_str
        assert "1000" in repr_str
        assert "0.05" in repr_str


class TestPerformanceMethods:
    """Tests for Performance model methods."""

    def test_calculate_engagement_rate_basic(self):
        """Test basic engagement rate calculation."""
        performance = Performance()
        performance.views = 1000
        performance.likes = 50
        performance.comments = 10

        engagement = performance.calculate_engagement_rate()

        # (50 + 10) / 1000 = 0.06
        assert engagement == 0.06

    def test_calculate_engagement_rate_zero_views(self):
        """Test engagement rate with zero views."""
        performance = Performance()
        performance.views = 0
        performance.likes = 10
        performance.comments = 5

        engagement = performance.calculate_engagement_rate()
        assert engagement == 0.0

    def test_calculate_engagement_rate_returns_value(self):
        """Test that calculate_engagement_rate returns value."""
        performance = Performance()
        performance.views = 1000
        performance.likes = 100
        performance.comments = 20

        result = performance.calculate_engagement_rate()

        # (100 + 20) / 1000 = 0.12
        assert result == 0.12

    def test_calculate_engagement_rate_rounding(self):
        """Test engagement rate rounding."""
        performance = Performance()
        performance.views = 3
        performance.likes = 1
        performance.comments = 0

        engagement = performance.calculate_engagement_rate()

        # 1/3 = 0.333...
        assert round(engagement, 2) == 0.33


class TestPerformanceProperties:
    """Tests for Performance model properties."""

    def test_net_subscribers(self):
        """Test net_subscribers property."""
        performance = Performance()
        performance.subscribers_gained = 100
        performance.subscribers_lost = 20

        assert performance.net_subscribers == 80

    def test_net_subscribers_negative(self):
        """Test net_subscribers when more lost than gained."""
        performance = Performance()
        performance.subscribers_gained = 10
        performance.subscribers_lost = 50

        assert performance.net_subscribers == -40
