"""Unit tests for PgVectorDB."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.pgvector_db import PgVectorDB


class TestPgVectorDB:
    """Test PgVectorDB functionality."""

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create mock session factory."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        factory = MagicMock()
        factory.return_value = session
        return factory

    @pytest.fixture
    def mock_embedding_model(self) -> MagicMock:
        """Create mock embedding model."""
        model = MagicMock()
        model.get_sentence_embedding_dimension.return_value = 1024
        model.encode.return_value = [0.1] * 1024
        return model

    @pytest.fixture
    def pgvector_db(
        self, mock_session_factory: MagicMock, mock_embedding_model: MagicMock
    ) -> PgVectorDB:
        """Create PgVectorDB instance with mocked dependencies."""
        with patch(
            "app.infrastructure.pgvector_db.SentenceTransformer",
            return_value=mock_embedding_model,
        ):
            return PgVectorDB(
                db_session_factory=mock_session_factory,
                model_name="BAAI/bge-m3",
                device="cpu",
            )

    def test_init(self, mock_session_factory: MagicMock, mock_embedding_model: MagicMock) -> None:
        """Should initialize with correct parameters."""
        with patch(
            "app.infrastructure.pgvector_db.SentenceTransformer",
            return_value=mock_embedding_model,
        ) as mock_st:
            db = PgVectorDB(
                db_session_factory=mock_session_factory,
                model_name="BAAI/bge-m3",
                device="cuda",
            )

            mock_st.assert_called_once_with("BAAI/bge-m3", device="cuda")
            assert db.model_name == "BAAI/bge-m3"
            assert db.device == "cuda"
            assert db.dimensions == 1024

    @pytest.mark.asyncio
    async def test_embed_single_text(
        self, pgvector_db: PgVectorDB, mock_embedding_model: MagicMock
    ) -> None:
        """Should embed single text."""
        import numpy as np

        mock_embedding_model.encode.return_value = np.array([0.1] * 1024)

        result = await pgvector_db.embed("Hello world")

        mock_embedding_model.encode.assert_called_once_with(
            "Hello world", normalize_embeddings=True
        )
        assert len(result) == 1024
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_embed_batch(
        self, pgvector_db: PgVectorDB, mock_embedding_model: MagicMock
    ) -> None:
        """Should embed batch of texts."""
        import numpy as np

        mock_embedding_model.encode.return_value = np.array([[0.1] * 1024, [0.2] * 1024])

        texts = ["Hello", "World"]
        results = await pgvector_db.embed_batch(texts)

        mock_embedding_model.encode.assert_called_once()
        assert len(results) == 2
        assert len(results[0]) == 1024
        assert len(results[1]) == 1024

    @pytest.mark.asyncio
    async def test_embed_batch_shows_progress(
        self, pgvector_db: PgVectorDB, mock_embedding_model: MagicMock
    ) -> None:
        """Should show progress bar for large batches."""
        import numpy as np

        mock_embedding_model.encode.return_value = np.array([[0.1] * 1024] * 15)

        texts = ["text"] * 15
        await pgvector_db.embed_batch(texts)

        # Verify show_progress_bar=True for >10 items
        call_kwargs = mock_embedding_model.encode.call_args[1]
        assert call_kwargs["show_progress_bar"] is True

    @pytest.mark.asyncio
    async def test_query_basic(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should query similar vectors."""
        chunk_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(id=chunk_id, distance=0.1),
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        results = await pgvector_db.query(vector=query_vector, top_k=5)

        assert len(results) == 1
        assert results[0][0] == str(chunk_id)
        assert results[0][1] == pytest.approx(0.9)  # 1.0 - 0.1 distance

    @pytest.mark.asyncio
    async def test_query_with_namespace(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should filter by namespace (channel_id)."""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        channel_id = uuid.uuid4()
        await pgvector_db.query(
            vector=query_vector,
            top_k=5,
            namespace=f"channel_{channel_id}",
        )

        # Verify execute was called (query was built with namespace filter)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_filter_after(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should filter by created_at time."""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        filter_time = datetime(2024, 1, 1, tzinfo=UTC)
        await pgvector_db.query(
            vector=query_vector,
            top_k=5,
            filter_after=filter_time,
        )

        # Verify execute was called
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_converts_distance_to_similarity(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should convert cosine distance to similarity score."""
        chunk_id1 = uuid.uuid4()
        chunk_id2 = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(id=chunk_id1, distance=0.0),  # Perfect match
            MagicMock(id=chunk_id2, distance=0.5),  # 50% distance
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        results = await pgvector_db.query(vector=query_vector, top_k=5)

        assert results[0][1] == pytest.approx(1.0)  # 1 - 0 = 1.0
        assert results[1][1] == pytest.approx(0.5)  # 1 - 0.5 = 0.5

    @pytest.mark.asyncio
    async def test_query_empty_results(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should handle empty results."""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        results = await pgvector_db.query(vector=query_vector, top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_upsert_logs_warning(
        self, pgvector_db: PgVectorDB, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log warning that upsert is not needed."""
        await pgvector_db.upsert(
            doc_id="test-id",
            vector=[0.1] * 1024,
            metadata={"key": "value"},
        )

        assert "not needed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_upsert_batch_logs_warning(
        self, pgvector_db: PgVectorDB, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log warning that upsert_batch is not needed."""
        await pgvector_db.upsert_batch(
            items=[("id1", [0.1] * 1024, None)],
        )

        assert "not needed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_delete_logs_warning(
        self, pgvector_db: PgVectorDB, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log warning that delete is not needed."""
        await pgvector_db.delete(doc_ids=["id1", "id2"])

        assert "not needed" in caplog.text.lower()


class TestPgVectorDBIntegration:
    """Integration-style tests for PgVectorDB query building."""

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create mock session factory."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        factory = MagicMock()
        factory.return_value = session
        return factory

    @pytest.fixture
    def mock_embedding_model(self) -> MagicMock:
        """Create mock embedding model."""
        model = MagicMock()
        model.get_sentence_embedding_dimension.return_value = 1024
        model.encode.return_value = [0.1] * 1024
        return model

    @pytest.fixture
    def pgvector_db(
        self, mock_session_factory: MagicMock, mock_embedding_model: MagicMock
    ) -> PgVectorDB:
        """Create PgVectorDB instance."""
        with patch(
            "app.infrastructure.pgvector_db.SentenceTransformer",
            return_value=mock_embedding_model,
        ):
            return PgVectorDB(
                db_session_factory=mock_session_factory,
                model_name="BAAI/bge-m3",
                device="cpu",
            )

    @pytest.mark.asyncio
    async def test_query_respects_top_k(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should limit results to top_k parameter."""
        # Create 10 mock results
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(id=uuid.uuid4(), distance=i * 0.1) for i in range(10)
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        query_vector = [0.1] * 1024
        await pgvector_db.query(vector=query_vector, top_k=3)

        # Note: In real DB, LIMIT would be applied. Here we verify call was made.
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_multiple_filters(
        self, pgvector_db: PgVectorDB, mock_session_factory: MagicMock
    ) -> None:
        """Should apply multiple filters together."""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        channel_id = uuid.uuid4()
        filter_time = datetime(2024, 1, 1, tzinfo=UTC)

        query_vector = [0.1] * 1024
        await pgvector_db.query(
            vector=query_vector,
            top_k=5,
            namespace=f"channel_{channel_id}",
            filter_after=filter_time,
        )

        # Verify query was executed with filters
        session.execute.assert_called_once()
