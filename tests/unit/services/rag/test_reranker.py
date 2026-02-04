"""Unit tests for RAGReranker."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.config.rag import RetrievalConfig
from app.services.rag.reranker import RAGReranker

from .conftest import create_retrieval_result


class TestRAGReranker:
    """Test RAGReranker functionality."""

    @pytest.fixture
    def config(self) -> RetrievalConfig:
        """Create default retrieval config."""
        return RetrievalConfig(
            top_k=10,
            enable_reranking=True,
            reranker_model="BAAI/bge-reranker-v2-m3",
            enable_mmr=True,
            mmr_lambda=0.7,
        )

    @pytest.fixture
    def reranker(self, config: RetrievalConfig) -> RAGReranker:
        """Create RAGReranker."""
        return RAGReranker(config=config)

    @pytest.fixture
    def sample_results(self) -> list:
        """Create sample retrieval results."""
        return [
            create_retrieval_result(
                text="Python is a programming language.",
                score=0.9,
                embedding=[0.1] * 1024,
            ),
            create_retrieval_result(
                text="Java is also popular.",
                score=0.85,
                embedding=[0.2] * 1024,
            ),
            create_retrieval_result(
                text="Python supports multiple paradigms.",
                score=0.8,
                embedding=[0.15] * 1024,
            ),
            create_retrieval_result(
                text="JavaScript runs in browsers.",
                score=0.75,
                embedding=[0.3] * 1024,
            ),
            create_retrieval_result(
                text="Python has great libraries.",
                score=0.7,
                embedding=[0.12] * 1024,
            ),
        ]

    @pytest.mark.asyncio
    async def test_rerank_basic(
        self,
        reranker: RAGReranker,
        sample_results: list,
    ) -> None:
        """Should rerank results."""
        # Mock the reranker model
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.95, 0.7, 0.9, 0.6, 0.85]
        reranker._reranker_model = mock_model

        query = "What is Python?"
        reranked = await reranker.rerank(query, sample_results)

        assert len(reranked) > 0
        assert len(reranked) <= len(sample_results)

    @pytest.mark.asyncio
    async def test_rerank_respects_top_k(
        self,
        reranker: RAGReranker,
        sample_results: list,
    ) -> None:
        """Should limit results to top_k."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.95, 0.7, 0.9, 0.6, 0.85]
        reranker._reranker_model = mock_model

        query = "What is Python?"
        reranked = await reranker.rerank(query, sample_results, top_k=3)

        assert len(reranked) == 3

    @pytest.mark.asyncio
    async def test_rerank_empty_results(
        self,
        reranker: RAGReranker,
    ) -> None:
        """Should handle empty results."""
        query = "What is Python?"
        reranked = await reranker.rerank(query, [])

        assert reranked == []

    @pytest.mark.asyncio
    async def test_rerank_single_result(
        self,
        reranker: RAGReranker,
    ) -> None:
        """Should handle single result."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9]
        reranker._reranker_model = mock_model

        query = "What is Python?"
        single_result = [
            create_retrieval_result(
                text="Python is a language.",
                score=0.9,
                embedding=[0.1] * 1024,
            )
        ]

        reranked = await reranker.rerank(query, single_result)

        assert len(reranked) == 1

    @pytest.mark.asyncio
    async def test_reranking_disabled(
        self,
        sample_results: list,
    ) -> None:
        """Should return original results when reranking disabled."""
        config = RetrievalConfig(
            enable_reranking=False,
            top_k=10,
        )
        reranker = RAGReranker(config=config)
        query = "What is Python?"

        reranked = await reranker.rerank(query, sample_results)

        # Should return same results
        assert len(reranked) == len(sample_results)

    @pytest.mark.asyncio
    async def test_rerank_sorts_by_score(
        self,
        reranker: RAGReranker,
        sample_results: list,
    ) -> None:
        """Should sort results by new score."""
        mock_model = MagicMock()
        # Give different scores - third result should rank highest
        mock_model.predict.return_value = [0.5, 0.3, 0.95, 0.2, 0.4]
        reranker._reranker_model = mock_model

        query = "What is Python?"
        reranked = await reranker.rerank(query, sample_results)

        # Highest score should be first (after reranking, score = 0.95)
        assert reranked[0].score == 0.95

    def test_cosine_similarity(self, reranker: RAGReranker) -> None:
        """Should compute cosine similarity correctly using batch method."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([[1.0, 0.0, 0.0]])  # Matrix format for batch

        similarities = reranker._cosine_similarity_batch(vec1, vec2)

        assert abs(similarities[0] - 1.0) < 1e-6  # Should be 1.0 (identical)

    def test_cosine_similarity_orthogonal(self, reranker: RAGReranker) -> None:
        """Should return 0 for orthogonal vectors."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([[0.0, 1.0, 0.0]])  # Matrix format for batch

        similarities = reranker._cosine_similarity_batch(vec1, vec2)

        assert abs(similarities[0] - 0.0) < 1e-6  # Should be 0

    def test_cosine_similarity_opposite(self, reranker: RAGReranker) -> None:
        """Should return -1 for opposite vectors."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([[-1.0, 0.0, 0.0]])  # Matrix format for batch

        similarities = reranker._cosine_similarity_batch(vec1, vec2)

        assert abs(similarities[0] - (-1.0)) < 1e-6  # Should be -1

    def test_cosine_similarity_zero_vector(self, reranker: RAGReranker) -> None:
        """Should handle zero vector in matrix."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([[0.0, 0.0, 0.0]])  # Zero vector in matrix

        similarities = reranker._cosine_similarity_batch(vec1, vec2)

        # Zero vector norm causes division protection, result should be close to 0
        assert abs(similarities[0]) < 1e-6

    def test_cosine_similarity_batch(self, reranker: RAGReranker) -> None:
        """Should compute batch cosine similarity."""
        vec = np.array([1.0, 0.0, 0.0])
        matrix = np.array(
            [
                [1.0, 0.0, 0.0],  # Identical
                [0.0, 1.0, 0.0],  # Orthogonal
                [-1.0, 0.0, 0.0],  # Opposite
            ]
        )

        similarities = reranker._cosine_similarity_batch(vec, matrix)

        assert len(similarities) == 3
        assert abs(similarities[0] - 1.0) < 1e-6
        assert abs(similarities[1] - 0.0) < 1e-6
        assert abs(similarities[2] - (-1.0)) < 1e-6

    def test_cosine_similarity_batch_zero_query(self, reranker: RAGReranker) -> None:
        """Should handle zero query vector in batch."""
        vec = np.array([0.0, 0.0, 0.0])
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

        similarities = reranker._cosine_similarity_batch(vec, matrix)

        assert all(s == 0.0 for s in similarities)

    @pytest.mark.asyncio
    async def test_apply_mmr_empty_results(
        self,
        reranker: RAGReranker,
    ) -> None:
        """Should handle empty results in MMR."""
        query_embedding = [0.1] * 1024
        mmr_results = await reranker.apply_mmr(query_embedding, [])

        assert mmr_results == []

    @pytest.mark.asyncio
    async def test_apply_mmr_disabled(
        self,
    ) -> None:
        """Should return original results when MMR disabled."""
        config = RetrievalConfig(
            enable_mmr=False,
            top_k=10,
        )
        reranker = RAGReranker(config=config)

        results = [create_retrieval_result(text="Test", score=0.9, embedding=[0.1] * 1024)]
        query_embedding = [0.1] * 1024

        mmr_results = await reranker.apply_mmr(query_embedding, results)

        assert len(mmr_results) == len(results)

    def test_reranker_model_lazy_loading(self, reranker: RAGReranker) -> None:
        """Should lazy load the reranker model."""
        # Initially, model should not be loaded
        assert reranker._reranker_model is None

    @pytest.mark.asyncio
    async def test_rerank_error_handling(
        self,
        reranker: RAGReranker,
        sample_results: list,
    ) -> None:
        """Should handle reranking errors gracefully."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = Exception("Model error")
        reranker._reranker_model = mock_model

        query = "What is Python?"

        # Should handle error and return original results
        result = await reranker.rerank(query, sample_results)
        assert isinstance(result, list)
        # Returns original results on error
        assert len(result) == len(sample_results)
