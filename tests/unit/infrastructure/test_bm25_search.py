"""Unit tests for BM25Search."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.bm25_search import BM25Search


class TestBM25Search:
    """Test BM25Search functionality."""

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
    def bm25_search(self, mock_session_factory: MagicMock) -> BM25Search:
        """Create BM25Search instance."""
        return BM25Search(db_session_factory=mock_session_factory)

    def test_init(self, mock_session_factory: MagicMock) -> None:
        """Should initialize with session factory."""
        search = BM25Search(db_session_factory=mock_session_factory)
        assert search.db_session_factory is mock_session_factory

    def test_sanitize_query_basic(self, bm25_search: BM25Search) -> None:
        """Should sanitize basic query."""
        result = bm25_search._sanitize_query("hello world")
        assert result == "hello world"

    def test_sanitize_query_special_chars(self, bm25_search: BM25Search) -> None:
        """Should remove special characters."""
        result = bm25_search._sanitize_query("hello@world#test!")
        assert result == "helloworldtest"

    def test_sanitize_query_keeps_hyphen_underscore(self, bm25_search: BM25Search) -> None:
        """Should keep hyphens and underscores."""
        result = bm25_search._sanitize_query("hello-world_test")
        assert result == "hello-world_test"

    def test_sanitize_query_collapses_spaces(self, bm25_search: BM25Search) -> None:
        """Should collapse multiple spaces."""
        result = bm25_search._sanitize_query("hello   world")
        assert result == "hello world"

    def test_sanitize_query_strips_whitespace(self, bm25_search: BM25Search) -> None:
        """Should strip leading/trailing whitespace."""
        result = bm25_search._sanitize_query("  hello world  ")
        assert result == "hello world"

    def test_sanitize_query_empty(self, bm25_search: BM25Search) -> None:
        """Should return empty for all special chars."""
        result = bm25_search._sanitize_query("@#$%^&*()")
        assert result == ""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, bm25_search: BM25Search) -> None:
        """Should return empty list for empty query."""
        result = await bm25_search.search("")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_whitespace_query(self, bm25_search: BM25Search) -> None:
        """Should return empty list for whitespace query."""
        result = await bm25_search.search("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_special_chars_only(self, bm25_search: BM25Search) -> None:
        """Should return empty list for query with only special chars."""
        result = await bm25_search.search("@#$%^")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_basic(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should execute BM25 search and return results."""
        # Setup mock
        chunk_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (str(chunk_id), 2.5),
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        results = await bm25_search.search("python programming")

        # Verify
        assert len(results) == 1
        assert results[0][0] == str(chunk_id)
        assert results[0][1] == 1.0  # Normalized to 1.0 (max score)

    @pytest.mark.asyncio
    async def test_search_normalizes_scores(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should normalize scores to 0-1 range."""
        # Setup mock with varying scores
        chunk_id1 = uuid.uuid4()
        chunk_id2 = uuid.uuid4()
        chunk_id3 = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (str(chunk_id1), 10.0),  # Max score
            (str(chunk_id2), 5.0),  # Half
            (str(chunk_id3), 2.5),  # Quarter
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        results = await bm25_search.search("test query")

        # Verify normalization
        assert len(results) == 3
        assert results[0][1] == 1.0  # 10/10
        assert results[1][1] == 0.5  # 5/10
        assert results[2][1] == 0.25  # 2.5/10

    @pytest.mark.asyncio
    async def test_search_with_channel_id(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should filter by channel_id."""
        channel_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        await bm25_search.search("test", channel_id=channel_id)

        # Verify channel_id was passed to query
        call_args = session.execute.call_args
        params = call_args[0][1]  # Second positional arg is params dict
        assert "channel_id" in params
        assert params["channel_id"] == str(channel_id)

    @pytest.mark.asyncio
    async def test_search_with_filter_after(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should filter by created_at time."""
        filter_time = datetime(2024, 1, 1, tzinfo=UTC)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        await bm25_search.search("test", filter_after=filter_time)

        # Verify filter_after was passed
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert "filter_after" in params
        assert params["filter_after"] == filter_time

    @pytest.mark.asyncio
    async def test_search_with_top_k(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should limit results to top_k."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        await bm25_search.search("test", top_k=10)

        # Verify top_k was passed
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["top_k"] == 10

    @pytest.mark.asyncio
    async def test_search_handles_db_error(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should return empty list on database error."""
        session = mock_session_factory.return_value
        session.execute = AsyncMock(side_effect=Exception("DB error"))

        # Execute - should not raise
        results = await bm25_search.search("test query")

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should handle empty results from database."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute
        results = await bm25_search.search("nonexistent term")

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_search_handles_zero_max_score(
        self, bm25_search: BM25Search, mock_session_factory: MagicMock
    ) -> None:
        """Should handle zero max score without division error."""
        chunk_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (str(chunk_id), 0.0),
        ]

        session = mock_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        # Execute - should not raise ZeroDivisionError
        results = await bm25_search.search("test")

        # Should normalize with fallback
        assert len(results) == 1
        assert results[0][1] == 0.0  # 0.0 / 1.0 (fallback max)
