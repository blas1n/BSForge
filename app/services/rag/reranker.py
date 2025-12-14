"""RAG reranking services.

This module provides reranking using BGE-Reranker and MMR (Maximal Marginal Relevance)
for diversity in retrieved results.
"""

import numpy as np
from sentence_transformers import CrossEncoder

from app.config.rag import RetrievalConfig
from app.core.logging import get_logger
from app.services.rag.retriever import RetrievalResult

logger = get_logger(__name__)


class RAGReranker:
    """Reranker for RAG retrieval results.

    Provides two reranking strategies:
    1. Cross-encoder reranking using BGE-Reranker for precision
    2. MMR (Maximal Marginal Relevance) for diversity

    Attributes:
        config: Retrieval configuration
        reranker_model: CrossEncoder model (loaded lazily)
    """

    def __init__(self, config: RetrievalConfig):
        """Initialize RAGReranker.

        Args:
            config: Retrieval configuration
        """
        self.config = config
        self._reranker_model: CrossEncoder | None = None

    @property
    def reranker_model(self) -> CrossEncoder:
        """Get or load reranker model.

        Returns:
            CrossEncoder instance
        """
        if self._reranker_model is None:
            logger.info(f"Loading reranker model: {self.config.reranker_model}")
            self._reranker_model = CrossEncoder(self.config.reranker_model)
        return self._reranker_model

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Rerank results using cross-encoder.

        Uses BGE-Reranker to compute precise relevance scores for (query, chunk) pairs.

        Args:
            query: Search query
            results: List of retrieval results
            top_k: Number of top results to return (default: all)

        Returns:
            Reranked list of results sorted by relevance score
        """
        if not results:
            return results

        if not self.config.enable_reranking:
            logger.debug("Reranking disabled, returning original results")
            return results

        logger.info(f"Reranking {len(results)} results")

        try:
            # Prepare (query, chunk_text) pairs
            pairs = [(query, r.text) for r in results]

            # Compute relevance scores
            scores = self.reranker_model.predict(pairs)

            # Update scores and sort
            for result, score in zip(results, scores, strict=False):
                result.score = float(score)

            reranked = sorted(results, key=lambda r: r.score, reverse=True)

            if top_k:
                reranked = reranked[:top_k]

            logger.debug(
                f"Reranked {len(results)} → {len(reranked)} results",
                extra={"top_score": reranked[0].score if reranked else 0.0},
            )

            return reranked

        except Exception as e:
            logger.warning(
                f"Reranking failed, returning original results: {e}",
                exc_info=True,
            )
            return results

    async def apply_mmr(
        self,
        query_embedding: list[float],
        results: list[RetrievalResult],
        lambda_param: float | None = None,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Apply Maximal Marginal Relevance for diversity.

        MMR balances relevance and diversity:
        - High lambda (e.g., 0.7): Prioritize relevance
        - Low lambda (e.g., 0.3): Prioritize diversity

        Algorithm:
        1. Start with empty selected set
        2. For each iteration:
           - For each remaining result:
             - MMR = λ × relevance - (1-λ) × max_similarity_to_selected
           - Select result with highest MMR score
           - Move to selected set
        3. Return selected results

        Args:
            query_embedding: Query embedding vector
            results: List of retrieval results (must have embeddings loaded)
            lambda_param: MMR lambda parameter (default: from config)
            top_k: Number of results to return (default: all)

        Returns:
            Reranked list with diverse results
        """
        if not results:
            return results

        if not self.config.enable_mmr:
            logger.debug("MMR disabled, returning original results")
            return results

        if lambda_param is None:
            lambda_param = self.config.mmr_lambda

        logger.info(f"Applying MMR with lambda={lambda_param}")

        try:
            # Prepare embeddings
            result_embeddings = []
            for r in results:
                if r.chunk is None or r.chunk.embedding is None:
                    logger.warning(f"Result {r.chunk_id} missing embedding, skipping MMR")
                    return results
                # Convert pgvector Vector to list
                result_embeddings.append(r.chunk.embedding)

            result_embeddings_array = np.array(result_embeddings)
            query_embedding_array = np.array(query_embedding)

            # Compute relevance scores (cosine similarity with query)
            relevance_scores = self._cosine_similarity_batch(
                query_embedding_array, result_embeddings_array
            )

            # MMR algorithm
            selected_indices: list[int] = []
            remaining_indices = list(range(len(results)))

            num_to_select = top_k if top_k else len(results)

            for _ in range(min(num_to_select, len(results))):
                best_mmr_score = -float("inf")
                best_idx = -1

                for idx in remaining_indices:
                    # Relevance score
                    relevance = relevance_scores[idx]

                    # Max similarity to already selected results
                    if selected_indices:
                        selected_embeddings = result_embeddings_array[selected_indices]
                        similarities = self._cosine_similarity_batch(
                            result_embeddings_array[idx], selected_embeddings
                        )
                        max_similarity = float(np.max(similarities))
                    else:
                        max_similarity = 0.0

                    # MMR score
                    mmr_score = lambda_param * relevance - (1 - lambda_param) * max_similarity

                    if mmr_score > best_mmr_score:
                        best_mmr_score = mmr_score
                        best_idx = idx

                # Move best to selected
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)

            # Reorder results
            mmr_results = [results[idx] for idx in selected_indices]

            logger.debug(
                f"Applied MMR: {len(results)} → {len(mmr_results)} diverse results",
                extra={"lambda": lambda_param},
            )

            return mmr_results

        except Exception as e:
            logger.warning(
                f"MMR failed, returning original results: {e}",
                exc_info=True,
            )
            return results

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (-1 to 1)
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def _cosine_similarity_batch(self, vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between a vector and a matrix of vectors.

        Args:
            vec: Single vector (1D array)
            matrix: Matrix of vectors (2D array, each row is a vector)

        Returns:
            Array of cosine similarities
        """
        # Handle both 1D and 2D inputs
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)

        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)

        # Compute dot products
        dot_products = np.dot(matrix, vec.T).flatten()

        # Compute norms
        vec_norm = np.linalg.norm(vec)
        matrix_norms = np.linalg.norm(matrix, axis=1)

        # Handle zero norms
        if vec_norm == 0:
            return np.zeros(len(matrix))

        # Compute similarities
        similarities = dot_products / (vec_norm * matrix_norms + 1e-8)

        # Return as float64 array
        result: np.ndarray = np.asarray(similarities, dtype=np.float64)
        return result


__all__ = ["RAGReranker"]
