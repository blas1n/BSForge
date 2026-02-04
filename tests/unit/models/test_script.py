"""Unit tests for Script model structure and methods."""

import pytest

from app.models.scene import SceneScript, SceneType
from app.models.script import Script, ScriptStatus


class TestScriptStatus:
    """Tests for ScriptStatus enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert ScriptStatus.GENERATED.value == "generated"
        assert ScriptStatus.REVIEWED.value == "reviewed"
        assert ScriptStatus.APPROVED.value == "approved"
        assert ScriptStatus.REJECTED.value == "rejected"
        assert ScriptStatus.PRODUCED.value == "produced"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert ScriptStatus("generated") == ScriptStatus.GENERATED
        assert ScriptStatus("approved") == ScriptStatus.APPROVED
        assert ScriptStatus("produced") == ScriptStatus.PRODUCED

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ScriptStatus("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(ScriptStatus.GENERATED, str)
        assert ScriptStatus.GENERATED == "generated"


class TestScriptModel:
    """Tests for Script model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert Script.__tablename__ == "scripts"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = Script.__table__.columns
        required_columns = [
            "id",
            "channel_id",
            "topic_id",
            "script_text",
            "headline",
            "scenes",
            "estimated_duration",
            "word_count",
            "style_score",
            "hook_score",
            "forbidden_words",
            "quality_passed",
            "generation_model",
            "context_chunks_used",
            "generation_metadata",
            "status",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = Script.__table__.columns

        # channel_id FK
        channel_fks = list(columns["channel_id"].foreign_keys)
        assert len(channel_fks) == 1
        assert "channels.id" in str(channel_fks[0])

        # topic_id FK
        topic_fks = list(columns["topic_id"].foreign_keys)
        assert len(topic_fks) == 1
        assert "topics.id" in str(topic_fks[0])

    def test_foreign_keys_not_nullable(self):
        """Test that required foreign keys are not nullable."""
        columns = Script.__table__.columns
        assert columns["channel_id"].nullable is False
        assert columns["topic_id"].nullable is False

    def test_scenes_is_nullable(self):
        """Test that scenes column is nullable (for backward compat)."""
        columns = Script.__table__.columns
        assert columns["scenes"].nullable is True

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = Script.__table__.indexes
        index_names = [idx.name for idx in indexes]

        assert "idx_script_channel_status" in index_names
        assert "idx_script_quality" in index_names

    def test_repr(self):
        """Test string representation."""
        script = Script()
        script.id = "test-id"
        script.channel_id = "channel-123"
        script.status = ScriptStatus.GENERATED

        repr_str = repr(script)
        assert "Script" in repr_str
        assert "test-id" in repr_str
        # Status appears as enum name in repr
        assert "GENERATED" in repr_str


class TestScriptMethods:
    """Tests for Script model methods."""

    def test_has_scenes_true(self):
        """Test has_scenes returns True when scenes exist."""
        script = Script()
        script.scenes = [
            {"scene_type": "hook", "text": "Hello"},
            {"scene_type": "content", "text": "World"},
        ]
        assert script.has_scenes is True

    def test_has_scenes_false_none(self):
        """Test has_scenes returns False when scenes is None."""
        script = Script()
        script.scenes = None
        assert script.has_scenes is False

    def test_has_scenes_false_empty(self):
        """Test has_scenes returns False when scenes is empty list."""
        script = Script()
        script.scenes = []
        assert script.has_scenes is False

    def test_get_scene_script_returns_none_when_no_scenes(self):
        """Test get_scene_script returns None when no scenes."""
        script = Script()
        script.scenes = None
        script.headline = "Test"
        assert script.get_scene_script() is None

        script.scenes = []
        assert script.get_scene_script() is None

    def test_get_scene_script_parses_scenes(self):
        """Test get_scene_script correctly parses scene data."""
        script = Script()
        script.headline = "Test Headline"
        script.scenes = [
            {"scene_type": "hook", "text": "Hook text"},
            {"scene_type": "content", "text": "Content text"},
        ]

        scene_script = script.get_scene_script()

        assert scene_script is not None
        assert isinstance(scene_script, SceneScript)
        assert scene_script.headline == "Test Headline"
        assert len(scene_script.scenes) == 2
        assert scene_script.scenes[0].scene_type == SceneType.HOOK
        assert scene_script.scenes[0].text == "Hook text"
        assert scene_script.scenes[1].scene_type == SceneType.CONTENT

    def test_get_scene_script_preserves_all_fields(self):
        """Test that get_scene_script preserves all scene fields."""
        script = Script()
        script.headline = "Headline"
        script.scenes = [
            {
                "scene_type": "commentary",
                "text": "My opinion",
                "visual_keyword": "thinking person",
                "transition_in": "fade",
                "emphasis_words": ["opinion"],
            }
        ]

        scene_script = script.get_scene_script()
        assert scene_script is not None

        scene = scene_script.scenes[0]
        assert scene.scene_type == SceneType.COMMENTARY
        assert scene.text == "My opinion"
        assert scene.visual_keyword == "thinking person"
        assert scene.transition_in == "fade"
        assert scene.emphasis_words == ["opinion"]
