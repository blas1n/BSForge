"""Unit tests for Video model structure."""

import pytest

from app.models.video import Video, VideoStatus


class TestVideoStatus:
    """Tests for VideoStatus enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert VideoStatus.GENERATING.value == "generating"
        assert VideoStatus.GENERATED.value == "generated"
        assert VideoStatus.REVIEWED.value == "reviewed"
        assert VideoStatus.APPROVED.value == "approved"
        assert VideoStatus.REJECTED.value == "rejected"
        assert VideoStatus.UPLOADED.value == "uploaded"
        assert VideoStatus.FAILED.value == "failed"
        assert VideoStatus.ARCHIVED.value == "archived"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert VideoStatus("generating") == VideoStatus.GENERATING
        assert VideoStatus("uploaded") == VideoStatus.UPLOADED
        assert VideoStatus("failed") == VideoStatus.FAILED

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            VideoStatus("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(VideoStatus.GENERATING, str)
        assert VideoStatus.GENERATING == "generating"

    def test_all_statuses_count(self):
        """Test that all expected statuses exist."""
        # Should have 8 distinct statuses
        all_statuses = list(VideoStatus)
        assert len(all_statuses) == 8


class TestVideoModel:
    """Tests for Video model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert Video.__tablename__ == "videos"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = Video.__table__.columns
        required_columns = [
            "id",
            "channel_id",
            "script_id",
            "video_path",
            "thumbnail_path",
            "audio_path",
            "subtitle_path",
            "duration_seconds",
            "file_size_bytes",
            "resolution",
            "fps",
            "tts_service",
            "tts_voice_id",
            "visual_sources",
            "generation_time_seconds",
            "generation_metadata",
            "error_message",
            "status",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = Video.__table__.columns

        # channel_id FK
        channel_fks = list(columns["channel_id"].foreign_keys)
        assert len(channel_fks) == 1
        assert "channels.id" in str(channel_fks[0])

        # script_id FK
        script_fks = list(columns["script_id"].foreign_keys)
        assert len(script_fks) == 1
        assert "scripts.id" in str(script_fks[0])

    def test_foreign_keys_not_nullable(self):
        """Test that required foreign keys are not nullable."""
        columns = Video.__table__.columns
        assert columns["channel_id"].nullable is False
        assert columns["script_id"].nullable is False

    def test_optional_paths_are_nullable(self):
        """Test that optional path columns are nullable."""
        columns = Video.__table__.columns
        assert columns["audio_path"].nullable is True
        assert columns["subtitle_path"].nullable is True

    def test_required_paths_not_nullable(self):
        """Test that required path columns are not nullable."""
        columns = Video.__table__.columns
        assert columns["video_path"].nullable is False
        assert columns["thumbnail_path"].nullable is False

    def test_metadata_nullable_fields(self):
        """Test nullable metadata fields."""
        columns = Video.__table__.columns
        assert columns["file_size_bytes"].nullable is True
        assert columns["generation_time_seconds"].nullable is True
        assert columns["error_message"].nullable is True

    def test_default_resolution(self):
        """Test default resolution is portrait (Shorts format)."""
        columns = Video.__table__.columns
        resolution_col = columns["resolution"]
        assert resolution_col.default.arg == "1080x1920"

    def test_default_fps(self):
        """Test default fps is 30."""
        columns = Video.__table__.columns
        fps_col = columns["fps"]
        assert fps_col.default.arg == 30

    def test_default_status(self):
        """Test default status is GENERATING."""
        columns = Video.__table__.columns
        status_col = columns["status"]
        assert status_col.default.arg == VideoStatus.GENERATING

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = Video.__table__.indexes
        index_names = [idx.name for idx in indexes]

        assert "idx_video_channel_status" in index_names
        assert "idx_video_script" in index_names

    def test_repr(self):
        """Test string representation."""
        video = Video()
        video.id = "test-id"
        video.script_id = "script-123"
        video.status = VideoStatus.GENERATED

        repr_str = repr(video)
        assert "Video" in repr_str
        assert "test-id" in repr_str
        # Status appears as enum name in repr
        assert "GENERATED" in repr_str


class TestVideoLifecycle:
    """Tests for Video status lifecycle."""

    def test_initial_status_is_generating(self):
        """Test that videos start in GENERATING status."""
        columns = Video.__table__.columns
        status_col = columns["status"]
        assert status_col.default.arg == VideoStatus.GENERATING

    def test_status_progression_happy_path(self):
        """Test expected status progression for successful video."""
        # This tests the enum values follow expected progression
        progression = [
            VideoStatus.GENERATING,
            VideoStatus.GENERATED,
            VideoStatus.REVIEWED,
            VideoStatus.APPROVED,
            VideoStatus.UPLOADED,
        ]
        # All statuses should be valid
        for status in progression:
            assert status in VideoStatus

    def test_status_progression_failure_path(self):
        """Test expected status progression for failed video."""
        progression = [
            VideoStatus.GENERATING,
            VideoStatus.FAILED,
        ]
        for status in progression:
            assert status in VideoStatus

    def test_status_can_be_rejected(self):
        """Test that REJECTED status exists for review rejection."""
        assert VideoStatus.REJECTED in VideoStatus
        assert VideoStatus.REJECTED.value == "rejected"

    def test_status_can_be_archived(self):
        """Test that ARCHIVED status exists."""
        assert VideoStatus.ARCHIVED in VideoStatus
        assert VideoStatus.ARCHIVED.value == "archived"
