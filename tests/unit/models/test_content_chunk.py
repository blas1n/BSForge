"""Unit tests for ContentChunk model enums and structure."""

import pytest

from app.models.content_chunk import (
    ChunkPosition,
    ContentChunk,
    ContentType,
)


class TestChunkPosition:
    """Tests for ChunkPosition enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert ChunkPosition.HOOK.value == "hook"
        assert ChunkPosition.BODY.value == "body"
        assert ChunkPosition.CONCLUSION.value == "conclusion"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert ChunkPosition("hook") == ChunkPosition.HOOK
        assert ChunkPosition("body") == ChunkPosition.BODY
        assert ChunkPosition("conclusion") == ChunkPosition.CONCLUSION

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ChunkPosition("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(ChunkPosition.HOOK, str)
        assert ChunkPosition.HOOK == "hook"


class TestContentType:
    """Tests for ContentType enum."""

    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert ContentType.SCRIPT.value == "script"
        assert ContentType.DRAFT.value == "draft"
        assert ContentType.OUTLINE.value == "outline"
        assert ContentType.NOTE.value == "note"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert ContentType("script") == ContentType.SCRIPT
        assert ContentType("draft") == ContentType.DRAFT
        assert ContentType("outline") == ContentType.OUTLINE
        assert ContentType("note") == ContentType.NOTE

    def test_invalid_value_raises(self):
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ContentType("invalid")

    def test_is_string_enum(self):
        """Test that enum is a string enum."""
        assert isinstance(ContentType.SCRIPT, str)
        assert ContentType.SCRIPT == "script"


class TestContentChunkModel:
    """Tests for ContentChunk model structure."""

    def test_tablename(self):
        """Test table name is correct."""
        assert ContentChunk.__tablename__ == "content_chunks"

    def test_has_required_columns(self):
        """Test that model has all required columns."""
        columns = ContentChunk.__table__.columns
        required_columns = [
            "id",
            "channel_id",
            "script_id",
            "content_type",
            "text",
            "chunk_index",
            "position",
            "context_before",
            "context_after",
            "is_opinion",
            "is_example",
            "is_analogy",
            "terms",
            "embedding",
            "embedding_model",
            "performance_score",
            "created_at",
            "updated_at",
        ]
        for col_name in required_columns:
            assert col_name in columns, f"Missing column: {col_name}"

    def test_has_foreign_keys(self):
        """Test that foreign keys are defined."""
        columns = ContentChunk.__table__.columns

        # channel_id FK
        channel_fks = list(columns["channel_id"].foreign_keys)
        assert len(channel_fks) == 1
        assert "channels.id" in str(channel_fks[0])

        # script_id FK (nullable)
        script_fks = list(columns["script_id"].foreign_keys)
        assert len(script_fks) == 1
        assert "scripts.id" in str(script_fks[0])

    def test_script_id_is_nullable(self):
        """Test that script_id is nullable (for non-script content)."""
        columns = ContentChunk.__table__.columns
        assert columns["script_id"].nullable is True

    def test_channel_id_not_nullable(self):
        """Test that channel_id is not nullable."""
        columns = ContentChunk.__table__.columns
        assert columns["channel_id"].nullable is False

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = ContentChunk.__table__.indexes
        index_names = [idx.name for idx in indexes]

        # Check key indexes exist
        assert "idx_chunk_channel_type" in index_names
        assert "idx_chunk_characteristics" in index_names
        assert "idx_chunk_performance" in index_names
        assert "idx_chunk_embedding_hnsw" in index_names

    def test_repr(self):
        """Test string representation."""
        chunk = ContentChunk()
        chunk.id = "test-id"
        chunk.content_type = ContentType.SCRIPT
        chunk.position = ChunkPosition.HOOK

        repr_str = repr(chunk)
        assert "ContentChunk" in repr_str
        assert "test-id" in repr_str

    def test_embedding_dimension(self):
        """Test that embedding column has correct dimension."""
        columns = ContentChunk.__table__.columns
        embedding_col = columns["embedding"]
        # pgvector Vector type stores dimension
        assert embedding_col.type.dim == 1024  # BGE-M3 dimension
