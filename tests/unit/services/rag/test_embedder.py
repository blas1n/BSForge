"""Unit tests for ContentEmbedder."""

from unittest.mock import AsyncMock

import pytest

from app.config.rag import EmbeddingConfig
from app.models.content_chunk import ChunkPosition
from app.services.rag.embedder import ContentEmbedder


class TestContentEmbedder:
    """Test ContentEmbedder functionality."""

    @pytest.fixture
    def mock_vector_db(self) -> AsyncMock:
        """Create mock VectorDB."""
        db = AsyncMock()
        db.embed.return_value = [0.1] * 1024  # BGE-M3 dimension
        db.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]
        return db

    @pytest.fixture
    def config(self) -> EmbeddingConfig:
        """Create default embedding config."""
        return EmbeddingConfig(
            model_name="BAAI/bge-m3",
            dimensions=1024,
            batch_size=32,
        )

    @pytest.fixture
    def embedder(self, mock_vector_db: AsyncMock, config: EmbeddingConfig) -> ContentEmbedder:
        """Create ContentEmbedder with mock VectorDB."""
        return ContentEmbedder(vector_db=mock_vector_db, config=config)

    @pytest.mark.asyncio
    async def test_embed_chunk_basic(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should embed text and return vector."""
        text = "Python is a great programming language."

        result = await embedder.embed_chunk(text)

        assert isinstance(result, list)
        assert len(result) == 1024
        mock_vector_db.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_chunk_with_position_hook(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should add [HOOK] tag for hook position."""
        text = "Have you ever wondered why?"

        await embedder.embed_chunk(text, position=ChunkPosition.HOOK)

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[HOOK]" in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_with_position_conclusion(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should add [CONCLUSION] tag for conclusion position."""
        text = "That's why Python is amazing."

        await embedder.embed_chunk(text, position=ChunkPosition.CONCLUSION)

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[CONCLUSION]" in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_with_opinion_flag(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should add [OPINION] tag when is_opinion is True."""
        text = "I think Python is the best."

        await embedder.embed_chunk(text, is_opinion=True)

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[OPINION]" in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_with_example_flag(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should add [EXAMPLE] tag when is_example is True."""
        text = "For example, consider this case."

        await embedder.embed_chunk(text, is_example=True)

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[EXAMPLE]" in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_with_keywords(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should add keywords tag."""
        text = "Python is widely used."
        keywords = ["python", "programming", "language"]

        await embedder.embed_chunk(text, keywords=keywords)

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[KEYWORDS:" in call_args
        assert "python" in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_limits_keywords(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should limit keywords to 5."""
        text = "Some text."
        keywords = ["one", "two", "three", "four", "five", "six", "seven"]

        await embedder.embed_chunk(text, keywords=keywords)

        call_args = mock_vector_db.embed.call_args[0][0]
        # Should only include first 5
        assert "six" not in call_args
        assert "seven" not in call_args

    @pytest.mark.asyncio
    async def test_embed_chunk_with_all_metadata(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should combine all metadata tags."""
        text = "Test content."

        await embedder.embed_chunk(
            text,
            position=ChunkPosition.HOOK,
            is_opinion=True,
            is_example=True,
            keywords=["test", "content"],
        )

        call_args = mock_vector_db.embed.call_args[0][0]
        assert "[HOOK]" in call_args
        assert "[OPINION]" in call_args
        assert "[EXAMPLE]" in call_args
        assert "[KEYWORDS:" in call_args
        assert "Test content." in call_args

    @pytest.mark.asyncio
    async def test_embed_batch(self, embedder: ContentEmbedder, mock_vector_db: AsyncMock) -> None:
        """Should embed multiple chunks in batch."""
        chunks = [
            ("First chunk", {"position": ChunkPosition.HOOK, "is_opinion": True}),
            ("Second chunk", {"position": ChunkPosition.BODY, "is_example": True}),
        ]

        results = await embedder.embed_batch(chunks)

        assert len(results) == 2
        mock_vector_db.embed_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_batch_with_metadata(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should apply metadata to each chunk in batch."""
        chunks = [
            (
                "Opinion text",
                {
                    "position": ChunkPosition.BODY,
                    "is_opinion": True,
                    "is_example": False,
                    "keywords": ["test"],
                },
            ),
        ]

        await embedder.embed_batch(chunks)

        call_args = mock_vector_db.embed_batch.call_args[0][0]
        assert len(call_args) == 1
        assert "[OPINION]" in call_args[0]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(
        self, embedder: ContentEmbedder, mock_vector_db: AsyncMock
    ) -> None:
        """Should handle empty batch."""
        mock_vector_db.embed_batch.return_value = []

        results = await embedder.embed_batch([])

        assert results == []

    def test_prepare_text_no_metadata(self, embedder: ContentEmbedder) -> None:
        """Should return original text when no metadata."""
        text = "Original text."

        result = embedder._prepare_text(
            text=text,
            position=None,
            is_opinion=False,
            is_example=False,
            keywords=None,
        )

        assert result == text

    def test_prepare_text_body_position_no_tag(self, embedder: ContentEmbedder) -> None:
        """Should not add tag for BODY position."""
        text = "Body text."

        result = embedder._prepare_text(
            text=text,
            position=ChunkPosition.BODY,
            is_opinion=False,
            is_example=False,
            keywords=None,
        )

        assert "[BODY]" not in result
        assert result == text

    def test_default_config(self, mock_vector_db: AsyncMock) -> None:
        """Should use default config when not provided."""
        embedder = ContentEmbedder(vector_db=mock_vector_db)

        assert embedder.config is not None
        assert embedder.config.model_name == "BAAI/bge-m3"
        assert embedder.config.dimensions == 1024
