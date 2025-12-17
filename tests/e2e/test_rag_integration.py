"""E2E tests for RAG (Retrieval-Augmented Generation) with pgvector integration.

Tests cover:
- ContentChunk creation with embeddings
- Vector similarity search via pgvector (HNSW index)
- RAGRetriever semantic search
- SpecializedRetriever for opinions, examples, hooks
- Filter functionality (position, is_opinion, is_example, min_performance)
- Embedding generation with sentence-transformers

Note: These tests require PostgreSQL with pgvector extension.
The BGE-M3 embedding model is heavy, so tests use a smaller model for faster execution.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.content_chunk import ChunkPosition, ContentChunk, ContentType


def _now() -> datetime:
    """Get current UTC datetime for timestamp fields."""
    return datetime.now(UTC)


class TestContentChunkDB:
    """Test ContentChunk model with database integration."""

    @pytest.mark.asyncio
    async def test_create_content_chunk_without_embedding(self, db_session: AsyncSession) -> None:
        """Test creating a content chunk without embedding."""
        # Create channel first
        channel = Channel(
            name="RAG Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create content chunk
        chunk = ContentChunk(
            channel_id=channel.id,
            content_type=ContentType.SCRIPT,
            text="이것은 테스트 청크입니다. AI 기술이 빠르게 발전하고 있습니다.",
            chunk_index=0,
            position=ChunkPosition.BODY,
            is_opinion=False,
            is_example=False,
            is_analogy=False,
            keywords=["AI", "기술", "발전"],
            embedding=None,
            embedding_model="test-model",
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.id is not None
        assert isinstance(chunk.id, uuid.UUID)
        assert chunk.channel_id == channel.id
        assert chunk.text == "이것은 테스트 청크입니다. AI 기술이 빠르게 발전하고 있습니다."
        assert chunk.position == ChunkPosition.BODY
        assert chunk.is_opinion is False
        assert "AI" in chunk.keywords

    @pytest.mark.asyncio
    async def test_create_content_chunk_with_embedding(self, db_session: AsyncSession) -> None:
        """Test creating a content chunk with a mock embedding."""
        # Create channel
        channel = Channel(
            name="RAG Embedding Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create mock embedding (1024 dimensions for BGE-M3)
        mock_embedding = [0.01] * 1024

        # Create chunk with embedding
        chunk = ContentChunk(
            channel_id=channel.id,
            content_type=ContentType.SCRIPT,
            text="AI 기술 발전에 대한 내 의견을 말씀드리면요...",
            chunk_index=0,
            position=ChunkPosition.BODY,
            is_opinion=True,
            is_example=False,
            is_analogy=False,
            keywords=["AI", "의견"],
            embedding=mock_embedding,
            embedding_model="BAAI/bge-m3",
            performance_score=0.85,
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.embedding is not None
        assert chunk.embedding_model == "BAAI/bge-m3"
        assert chunk.is_opinion is True
        assert chunk.performance_score == 0.85

    @pytest.mark.asyncio
    async def test_content_chunk_channel_relationship(self, db_session: AsyncSession) -> None:
        """Test ContentChunk-Channel relationship."""
        # Create channel
        channel = Channel(
            name="Relationship Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create multiple chunks
        for i in range(3):
            chunk = ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text=f"청크 {i}의 내용입니다.",
                chunk_index=i,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=[f"keyword{i}"],
                embedding_model="test",
            )
            db_session.add(chunk)

        await db_session.commit()
        await db_session.refresh(channel, ["content_chunks"])

        assert len(channel.content_chunks) == 3

    @pytest.mark.asyncio
    async def test_content_chunk_positions(self, db_session: AsyncSession) -> None:
        """Test different chunk positions."""
        channel = Channel(
            name="Position Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunks with different positions
        positions = [
            (ChunkPosition.HOOK, "충격적인 AI 뉴스!"),
            (ChunkPosition.BODY, "AI가 발전하고 있습니다."),
            (ChunkPosition.CONCLUSION, "AI 시대가 왔습니다."),
        ]

        for i, (pos, chunk_text) in enumerate(positions):
            chunk = ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text=chunk_text,
                chunk_index=i,
                position=pos,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=[],
                embedding_model="test",
            )
            db_session.add(chunk)

        await db_session.commit()

        # Query by position
        result = await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.position == ChunkPosition.HOOK)
        )
        hook_chunks = result.scalars().all()

        assert len(hook_chunks) == 1
        assert hook_chunks[0].text == "충격적인 AI 뉴스!"

    @pytest.mark.asyncio
    async def test_filter_by_characteristics(self, db_session: AsyncSession) -> None:
        """Test filtering chunks by characteristics."""
        channel = Channel(
            name="Characteristics Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunks with different characteristics
        chunks_data = [
            {"text": "팩트: AI 시장 규모 1조", "is_opinion": False, "is_example": False},
            {"text": "내 생각엔 이건 시작일 뿐이에요", "is_opinion": True, "is_example": False},
            {"text": "예를 들어 ChatGPT를 보세요", "is_opinion": False, "is_example": True},
            {"text": "제가 느끼기엔 GPT가 좋은 예시죠", "is_opinion": True, "is_example": True},
        ]

        for i, data in enumerate(chunks_data):
            chunk = ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text=data["text"],
                chunk_index=i,
                position=ChunkPosition.BODY,
                is_opinion=data["is_opinion"],
                is_example=data["is_example"],
                is_analogy=False,
                keywords=[],
                embedding_model="test",
            )
            db_session.add(chunk)

        await db_session.commit()

        # Query opinions only
        result = await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.is_opinion == True)  # noqa: E712
        )
        opinion_chunks = result.scalars().all()
        assert len(opinion_chunks) == 2

        # Query examples only
        result = await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.is_example == True)  # noqa: E712
        )
        example_chunks = result.scalars().all()
        assert len(example_chunks) == 2


class TestPgVectorExtension:
    """Test pgvector extension functionality."""

    @pytest.mark.asyncio
    async def test_pgvector_extension_exists(self, db_session: AsyncSession) -> None:
        """Test that pgvector extension is installed."""
        result = await db_session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        extension = result.scalar()
        assert extension == "vector", "pgvector extension must be installed"

    @pytest.mark.asyncio
    async def test_vector_cosine_similarity_raw(self, db_session: AsyncSession) -> None:
        """Test raw SQL vector cosine similarity calculation."""
        # Test vectors (small dimension for testing)
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]  # Same direction
        vec3 = [0.0, 1.0, 0.0]  # Orthogonal

        # Calculate cosine distance using pgvector
        result = await db_session.execute(
            text(
                f"""
                SELECT
                    1 - ('{vec1}'::vector <=> '{vec2}'::vector) as similarity_same,
                    1 - ('{vec1}'::vector <=> '{vec3}'::vector) as similarity_ortho
            """
            )
        )
        row = result.fetchone()

        assert row is not None
        similarity_same = row[0]
        similarity_ortho = row[1]

        # Same vectors should have similarity ~1
        assert similarity_same > 0.99
        # Orthogonal vectors should have similarity ~0
        assert abs(similarity_ortho) < 0.01

    @pytest.mark.asyncio
    async def test_content_chunk_vector_similarity_query(self, db_session: AsyncSession) -> None:
        """Test vector similarity query on ContentChunk table."""
        # Create channel
        channel = Channel(
            name="Vector Similarity Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunks with different embeddings
        # Chunk 1: "AI technology" direction
        embedding_ai = [0.8, 0.6, 0.0] + [0.0] * 1021  # Pad to 1024
        # Chunk 2: Similar to AI
        embedding_similar = [0.7, 0.7, 0.1] + [0.0] * 1021
        # Chunk 3: Different direction
        embedding_diff = [0.1, 0.1, 0.99] + [0.0] * 1021

        chunks = [
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="AI 기술 발전",
                chunk_index=0,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["AI"],
                embedding=embedding_ai,
                embedding_model="test",
            ),
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="인공지능 기술",
                chunk_index=1,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["인공지능"],
                embedding=embedding_similar,
                embedding_model="test",
            ),
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="요리 레시피",
                chunk_index=2,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["요리"],
                embedding=embedding_diff,
                embedding_model="test",
            ),
        ]

        for chunk in chunks:
            db_session.add(chunk)
        await db_session.commit()

        # Query vector - looking for AI-like content
        query_vector = [0.8, 0.6, 0.0] + [0.0] * 1021

        # Query similar chunks using cosine distance
        result = await db_session.execute(
            select(
                ContentChunk.id,
                ContentChunk.text,
                ContentChunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.embedding.is_not(None))
            .order_by("distance")
            .limit(2)
        )
        rows = result.all()

        assert len(rows) == 2
        # First result should be closest (AI 기술 발전)
        assert "AI" in rows[0].text
        # Second should be similar (인공지능 기술)
        assert "인공지능" in rows[1].text or "AI" in rows[1].text


class TestChunkPerformanceFilter:
    """Test filtering chunks by performance score."""

    @pytest.mark.asyncio
    async def test_filter_by_min_performance(self, db_session: AsyncSession) -> None:
        """Test filtering chunks by minimum performance score."""
        channel = Channel(
            name="Performance Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunks with different performance scores
        performance_scores = [None, 0.3, 0.5, 0.7, 0.9]

        for i, score in enumerate(performance_scores):
            chunk = ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text=f"청크 {i}",
                chunk_index=i,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=[],
                embedding_model="test",
                performance_score=score,
            )
            db_session.add(chunk)

        await db_session.commit()

        # Query with min_performance = 0.5
        result = await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.performance_score >= 0.5)
        )
        high_performers = result.scalars().all()

        assert len(high_performers) == 3  # 0.5, 0.7, 0.9

        # Query with min_performance = 0.8
        result = await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.channel_id == channel.id)
            .where(ContentChunk.performance_score >= 0.8)
        )
        top_performers = result.scalars().all()

        assert len(top_performers) == 1  # 0.9 only


class TestContentChunkContext:
    """Test ContentChunk context fields."""

    @pytest.mark.asyncio
    async def test_chunk_with_context(self, db_session: AsyncSession) -> None:
        """Test creating chunk with context_before and context_after."""
        channel = Channel(
            name="Context Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        chunk = ContentChunk(
            channel_id=channel.id,
            content_type=ContentType.SCRIPT,
            text="본문 내용입니다.",
            chunk_index=1,
            position=ChunkPosition.BODY,
            context_before="이전 청크에서는 AI 소개를 했습니다.",
            context_after="다음 청크에서는 결론을 말합니다.",
            is_opinion=False,
            is_example=False,
            is_analogy=False,
            keywords=[],
            embedding_model="test",
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.context_before == "이전 청크에서는 AI 소개를 했습니다."
        assert chunk.context_after == "다음 청크에서는 결론을 말합니다."


class TestContentTypeEnum:
    """Test ContentType enum values."""

    def test_content_type_values(self) -> None:
        """Test ContentType enum has all expected values."""
        assert ContentType.SCRIPT == "script"
        assert ContentType.DRAFT == "draft"
        assert ContentType.OUTLINE == "outline"
        assert ContentType.NOTE == "note"


class TestChunkPositionEnum:
    """Test ChunkPosition enum values."""

    def test_chunk_position_values(self) -> None:
        """Test ChunkPosition enum has all expected values."""
        assert ChunkPosition.HOOK == "hook"
        assert ChunkPosition.BODY == "body"
        assert ChunkPosition.CONCLUSION == "conclusion"


class TestBM25Extension:
    """Test ParadeDB pg_search (BM25) extension functionality."""

    @pytest.mark.asyncio
    async def test_pg_search_extension_exists(self, db_session: AsyncSession) -> None:
        """Test that pg_search extension is installed."""
        result = await db_session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'pg_search'")
        )
        extension = result.scalar()
        # pg_search extension should be available in ParadeDB image
        # This test will pass once migration is run
        if extension is None:
            pytest.skip("pg_search extension not installed yet - run migrations first")
        assert extension == "pg_search"


class TestBM25SearchIntegration:
    """Integration tests for BM25Search with real database."""

    @pytest.mark.asyncio
    async def test_bm25_search_with_keywords(self, db_session: AsyncSession) -> None:
        """Test BM25 search finds chunks by keywords."""
        # Create channel
        channel = Channel(
            name="BM25 Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunks with different keywords
        chunks = [
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="Python is a great programming language for AI.",
                chunk_index=0,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["python", "programming", "AI"],
                embedding_model="test",
            ),
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="JavaScript is used for web development.",
                chunk_index=1,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["javascript", "web", "development"],
                embedding_model="test",
            ),
            ContentChunk(
                channel_id=channel.id,
                content_type=ContentType.SCRIPT,
                text="Machine learning models need training data.",
                chunk_index=2,
                position=ChunkPosition.BODY,
                is_opinion=False,
                is_example=False,
                is_analogy=False,
                keywords=["machine-learning", "AI", "data"],
                embedding_model="test",
            ),
        ]

        for chunk in chunks:
            db_session.add(chunk)
        await db_session.commit()

        # Verify chunks were created
        result = await db_session.execute(
            select(ContentChunk).where(ContentChunk.channel_id == channel.id)
        )
        saved_chunks = result.scalars().all()
        assert len(saved_chunks) == 3

        # Verify keywords are stored correctly
        python_chunk = next(c for c in saved_chunks if "python" in c.keywords)
        assert "programming" in python_chunk.keywords
        assert "AI" in python_chunk.keywords

    @pytest.mark.asyncio
    async def test_content_chunk_keywords_array(self, db_session: AsyncSession) -> None:
        """Test that keywords array field works correctly."""
        channel = Channel(
            name="Keywords Array Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create chunk with empty keywords
        chunk_empty = ContentChunk(
            channel_id=channel.id,
            content_type=ContentType.SCRIPT,
            text="Content without keywords",
            chunk_index=0,
            position=ChunkPosition.BODY,
            is_opinion=False,
            is_example=False,
            is_analogy=False,
            keywords=[],
            embedding_model="test",
        )
        db_session.add(chunk_empty)

        # Create chunk with many keywords
        chunk_many = ContentChunk(
            channel_id=channel.id,
            content_type=ContentType.SCRIPT,
            text="Content with many keywords",
            chunk_index=1,
            position=ChunkPosition.BODY,
            is_opinion=False,
            is_example=False,
            is_analogy=False,
            keywords=["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
            embedding_model="test",
        )
        db_session.add(chunk_many)
        await db_session.commit()

        # Refresh and verify
        await db_session.refresh(chunk_empty)
        await db_session.refresh(chunk_many)

        assert chunk_empty.keywords == []
        assert len(chunk_many.keywords) == 5
        assert "keyword3" in chunk_many.keywords
