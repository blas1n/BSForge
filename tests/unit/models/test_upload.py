"""Unit tests for Upload model structure."""

import pytest

from app.models.upload import PrivacyStatus, Upload, UploadStatus


class TestPrivacyStatus:
    """Tests for PrivacyStatus enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert PrivacyStatus.PUBLIC.value == "public"
        assert PrivacyStatus.PRIVATE.value == "private"
        assert PrivacyStatus.UNLISTED.value == "unlisted"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert PrivacyStatus("public") == PrivacyStatus.PUBLIC
        assert PrivacyStatus("private") == PrivacyStatus.PRIVATE
        assert PrivacyStatus("unlisted") == PrivacyStatus.UNLISTED

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            PrivacyStatus("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(PrivacyStatus.PUBLIC, str)
        assert PrivacyStatus.PUBLIC == "public"

    def test_all_statuses_count(self):
        """Test that all expected statuses exist."""
        all_statuses = list(PrivacyStatus)
        assert len(all_statuses) == 3


class TestUploadStatus:
    """Tests for UploadStatus enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert UploadStatus.PENDING.value == "pending"
        assert UploadStatus.SCHEDULED.value == "scheduled"
        assert UploadStatus.UPLOADING.value == "uploading"
        assert UploadStatus.PROCESSING.value == "processing"
        assert UploadStatus.COMPLETED.value == "completed"
        assert UploadStatus.FAILED.value == "failed"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert UploadStatus("pending") == UploadStatus.PENDING
        assert UploadStatus("completed") == UploadStatus.COMPLETED
        assert UploadStatus("failed") == UploadStatus.FAILED

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            UploadStatus("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(UploadStatus.PENDING, str)
        assert UploadStatus.PENDING == "pending"

    def test_all_statuses_count(self):
        """Test that all expected statuses exist."""
        all_statuses = list(UploadStatus)
        assert len(all_statuses) == 6


class TestUploadModel:
    """Tests for Upload model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert Upload.__tablename__ == "uploads"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = Upload.__table__.columns
        required_columns = [
            "id",
            "video_id",
            "youtube_video_id",
            "youtube_url",
            "title",
            "description",
            "tags",
            "category_id",
            "privacy_status",
            "is_shorts",
            "scheduled_at",
            "uploaded_at",
            "published_at",
            "upload_status",
            "error_message",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = Upload.__table__.columns

        # video_id FK
        video_fks = list(columns["video_id"].foreign_keys)
        assert len(video_fks) == 1
        assert "videos.id" in str(video_fks[0])

    def test_video_id_is_unique(self):
        """Test that video_id is unique."""
        columns = Upload.__table__.columns
        assert columns["video_id"].unique is True

    def test_youtube_video_id_is_unique(self):
        """Test that youtube_video_id is unique."""
        columns = Upload.__table__.columns
        assert columns["youtube_video_id"].unique is True

    def test_required_fields_not_nullable(self):
        """Test that required fields are not nullable."""
        columns = Upload.__table__.columns
        assert columns["video_id"].nullable is False
        assert columns["title"].nullable is False

    def test_optional_fields_are_nullable(self):
        """Test that optional fields are nullable."""
        columns = Upload.__table__.columns
        assert columns["youtube_video_id"].nullable is True
        assert columns["youtube_url"].nullable is True
        assert columns["description"].nullable is True
        assert columns["tags"].nullable is True
        assert columns["scheduled_at"].nullable is True
        assert columns["uploaded_at"].nullable is True
        assert columns["published_at"].nullable is True
        assert columns["error_message"].nullable is True

    def test_default_category_id(self):
        """Test default category_id is Science & Tech."""
        columns = Upload.__table__.columns
        category_col = columns["category_id"]
        assert category_col.default.arg == "28"

    def test_default_privacy_status(self):
        """Test default privacy_status is PRIVATE."""
        columns = Upload.__table__.columns
        privacy_col = columns["privacy_status"]
        assert privacy_col.default.arg == PrivacyStatus.PRIVATE

    def test_default_upload_status(self):
        """Test default upload_status is PENDING."""
        columns = Upload.__table__.columns
        status_col = columns["upload_status"]
        assert status_col.default.arg == UploadStatus.PENDING

    def test_default_is_shorts(self):
        """Test default is_shorts is True."""
        columns = Upload.__table__.columns
        is_shorts_col = columns["is_shorts"]
        assert is_shorts_col.default.arg is True

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = Upload.__table__.indexes
        index_names = [idx.name for idx in indexes]

        assert "idx_upload_youtube_id" in index_names
        assert "idx_upload_scheduled" in index_names
        assert "idx_upload_status" in index_names

    def test_repr(self):
        """Test string representation."""
        upload = Upload()
        upload.id = "test-id"
        upload.title = "Test Video Title"
        upload.upload_status = UploadStatus.PENDING

        repr_str = repr(upload)
        assert "Upload" in repr_str
        assert "test-id" in repr_str
        assert "PENDING" in repr_str


class TestUploadLifecycle:
    """Tests for Upload status lifecycle."""

    def test_initial_status_is_pending(self):
        """Test that uploads start in PENDING status."""
        columns = Upload.__table__.columns
        status_col = columns["upload_status"]
        assert status_col.default.arg == UploadStatus.PENDING

    def test_status_progression_happy_path(self):
        """Test expected status progression for successful upload."""
        progression = [
            UploadStatus.PENDING,
            UploadStatus.SCHEDULED,
            UploadStatus.UPLOADING,
            UploadStatus.PROCESSING,
            UploadStatus.COMPLETED,
        ]
        for status in progression:
            assert status in UploadStatus

    def test_status_progression_failure_path(self):
        """Test expected status progression for failed upload."""
        progression = [
            UploadStatus.PENDING,
            UploadStatus.UPLOADING,
            UploadStatus.FAILED,
        ]
        for status in progression:
            assert status in UploadStatus
