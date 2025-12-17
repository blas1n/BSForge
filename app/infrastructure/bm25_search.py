"""BM25 keyword search using ParadeDB pg_search extension.

This module provides BM25-based keyword search on ContentChunk.keywords array
for hybrid RAG retrieval (semantic + keyword).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.core.logging import get_logger
from app.core.types import SessionFactory

logger = get_logger(__name__)


class BM25Search:
    """BM25 keyword search using ParadeDB pg_search.

    Provides BM25-based keyword search on ContentChunk.keywords array.
    Used in conjunction with semantic search for hybrid retrieval.

    Attributes:
        db_session_factory: Async session factory for database access
    """

    def __init__(self, db_session_factory: SessionFactory):
        """Initialize BM25Search.

        Args:
            db_session_factory: SQLAlchemy async session factory
        """
        self.db_session_factory = db_session_factory
        logger.info("BM25Search initialized")

    async def search(
        self,
        query: str,
        channel_id: uuid.UUID | None = None,
        top_k: int = 20,
        filter_after: datetime | None = None,
    ) -> list[tuple[str, float]]:
        """Search keywords using BM25.

        Args:
            query: Search query (English keywords)
            channel_id: Channel UUID to filter by
            top_k: Number of results to return
            filter_after: Only return chunks created after this time

        Returns:
            List of (chunk_id, normalized_score) tuples sorted by score descending.
            Scores are normalized to 0-1 range.
        """
        if not query or not query.strip():
            logger.debug("Empty query, returning empty results")
            return []

        # Sanitize query for BM25 search
        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            return []

        async with self.db_session_factory() as session:
            # Build the BM25 search query using ParadeDB syntax
            # ParadeDB uses @@@ operator for BM25 search
            sql = """
                SELECT
                    id::text,
                    paradedb.score(id) as bm25_score
                FROM content_chunks
                WHERE keywords @@@ :query
            """

            params: dict[str, Any] = {"query": sanitized_query}

            # Add channel filter
            if channel_id:
                sql += " AND channel_id = :channel_id"
                params["channel_id"] = str(channel_id)

            # Add time filter
            if filter_after:
                sql += " AND created_at >= :filter_after"
                params["filter_after"] = filter_after

            # Order by BM25 score and limit
            sql += " ORDER BY bm25_score DESC LIMIT :top_k"
            params["top_k"] = top_k

            try:
                result = await session.execute(text(sql), params)
                rows = result.fetchall()

                if not rows:
                    return []

                # Normalize scores to 0-1 range
                # BM25 scores can vary widely, so we normalize by max score
                max_score = max(row[1] for row in rows) if rows else 1.0
                if max_score <= 0:
                    max_score = 1.0

                normalized_results = [(row[0], row[1] / max_score) for row in rows]

                logger.debug(
                    f"BM25 search returned {len(normalized_results)} results",
                    extra={"query": query, "top_k": top_k},
                )

                return normalized_results

            except Exception as e:
                logger.warning(
                    f"BM25 search failed: {e}",
                    extra={"query": query, "error": str(e)},
                    exc_info=True,
                )
                return []

    def _sanitize_query(self, query: str) -> str:
        """Sanitize query for BM25 search.

        Removes special characters and prepares query for ParadeDB.

        Args:
            query: Raw query string

        Returns:
            Sanitized query string
        """
        # Remove special characters that might interfere with BM25 parsing
        # Keep alphanumeric, spaces, and common punctuation
        sanitized = "".join(c for c in query if c.isalnum() or c.isspace() or c in "-_")

        # Collapse multiple spaces
        sanitized = " ".join(sanitized.split())

        return sanitized.strip()


__all__ = ["BM25Search"]
