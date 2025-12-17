"""RAG retrieval services.

This module provides hybrid search (semantic + BM25) with query expansion
and specialized retrievers for opinions, examples, and hooks.
"""

import uuid
from datetime import datetime

from anthropic import AsyncAnthropic
from sqlalchemy import and_, select

from app.config.rag import QueryExpansionConfig, RetrievalConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.infrastructure.pgvector_db import PgVectorDB
from app.models.content_chunk import ChunkPosition, ContentChunk
from app.prompts.manager import PromptManager, PromptType, get_prompt_manager

logger = get_logger(__name__)


class RetrievalResult:
    """Single retrieval result with metadata.

    Attributes:
        chunk_id: ContentChunk UUID
        chunk: ContentChunk ORM object (loaded lazily)
        score: Similarity score (0-1)
        text: Chunk text content
        position: Chunk position (hook/body/conclusion)
        is_opinion: Whether chunk contains opinion
        is_example: Whether chunk contains examples
        performance_score: Performance score if available
    """

    def __init__(
        self,
        chunk_id: uuid.UUID,
        score: float,
        chunk: ContentChunk | None = None,
    ):
        """Initialize retrieval result.

        Args:
            chunk_id: ContentChunk UUID
            score: Similarity score (0-1)
            chunk: Optional ContentChunk object
        """
        self.chunk_id = chunk_id
        self.score = score
        self.chunk = chunk

    @property
    def text(self) -> str:
        """Get chunk text."""
        if self.chunk is None:
            raise ValueError("Chunk not loaded")
        return self.chunk.text

    @property
    def position(self) -> ChunkPosition:
        """Get chunk position."""
        if self.chunk is None:
            raise ValueError("Chunk not loaded")
        return self.chunk.position

    @property
    def is_opinion(self) -> bool:
        """Check if chunk contains opinion."""
        if self.chunk is None:
            raise ValueError("Chunk not loaded")
        return self.chunk.is_opinion

    @property
    def is_example(self) -> bool:
        """Check if chunk contains example."""
        if self.chunk is None:
            raise ValueError("Chunk not loaded")
        return self.chunk.is_example

    @property
    def performance_score(self) -> float | None:
        """Get performance score."""
        if self.chunk is None:
            raise ValueError("Chunk not loaded")
        return self.chunk.performance_score

    def __repr__(self) -> str:
        """String representation."""
        return f"<RetrievalResult(chunk_id={self.chunk_id}, score={self.score:.3f})>"


class RAGRetriever:
    """RAG retrieval with hybrid search and query expansion.

    Implements hybrid search combining:
    - Semantic search (70%): Vector similarity using embeddings
    - Keyword search (30%): BM25-style keyword matching (future)

    Supports query expansion using Claude API to generate related queries.

    Attributes:
        vector_db: PgVectorDB instance
        db_session_factory: AsyncSession factory
        retrieval_config: Retrieval configuration
        query_config: Query expansion configuration
        llm_client: Anthropic client for query expansion
    """

    def __init__(
        self,
        vector_db: PgVectorDB,
        db_session_factory: SessionFactory,
        retrieval_config: RetrievalConfig,
        query_config: QueryExpansionConfig,
        llm_client: AsyncAnthropic | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        """Initialize RAGRetriever.

        Args:
            vector_db: PgVectorDB instance
            db_session_factory: SQLAlchemy async session factory
            retrieval_config: Retrieval configuration
            query_config: Query expansion configuration
            llm_client: Optional Anthropic client for query expansion
            prompt_manager: Optional PromptManager for centralized prompt management
        """
        self.vector_db = vector_db
        self.db_session_factory = db_session_factory
        self.retrieval_config = retrieval_config
        self.query_config = query_config
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or get_prompt_manager()

    async def retrieve(
        self,
        query: str,
        channel_id: uuid.UUID,
        top_k: int | None = None,
        filter_after: datetime | None = None,
        content_types: list[str] | None = None,
        position: ChunkPosition | None = None,
        min_performance: float | None = None,
        is_opinion: bool | None = None,
        is_example: bool | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks using hybrid search.

        Args:
            query: Search query
            channel_id: Channel UUID to filter by
            top_k: Number of results (default: from config)
            filter_after: Only return chunks created after this time
            content_types: Filter by content types
            position: Filter by chunk position
            min_performance: Minimum performance score
            is_opinion: Filter by opinion chunks
            is_example: Filter by example chunks

        Returns:
            List of RetrievalResult objects sorted by score (descending)
        """
        if top_k is None:
            top_k = self.retrieval_config.final_top_k

        # Expand query if enabled
        queries = await self._expand_query(query) if self.query_config.enabled else [query]

        logger.info(
            f"Retrieving with {len(queries)} queries for channel {channel_id}",
            extra={"query": query, "expanded_count": len(queries)},
        )

        # Retrieve for each query
        all_results: dict[uuid.UUID, float] = {}
        for q in queries:
            # Generate query embedding
            query_vector = await self.vector_db.embed(q)

            # Semantic search via pgvector
            namespace = f"channel_{channel_id}"
            vector_results = await self.vector_db.query(
                vector=query_vector,
                top_k=self.retrieval_config.semantic_top_k,
                filter_after=filter_after,
                namespace=namespace,
            )

            # Merge results (sum scores for duplicates)
            for chunk_id_str, score in vector_results:
                chunk_id = uuid.UUID(chunk_id_str)
                # Weight by semantic_weight (default 0.7)
                weighted_score = score * self.retrieval_config.semantic_weight
                all_results[chunk_id] = all_results.get(chunk_id, 0.0) + weighted_score

        # TODO: Add BM25 keyword search (weighted by keyword_weight = 0.3)
        # This requires full-text search implementation in PostgreSQL
        # For now, semantic search only

        # Sort by score and take top_k
        sorted_results = sorted(all_results.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Build RetrievalResult objects
        results = [
            RetrievalResult(chunk_id=chunk_id, score=score) for chunk_id, score in sorted_results
        ]

        # Load ContentChunk objects with filters
        await self._load_chunks(
            results,
            channel_id=channel_id,
            content_types=content_types,
            position=position,
            min_performance=min_performance,
            is_opinion=is_opinion,
            is_example=is_example,
        )

        # Filter out results where chunk failed to load (filtered out)
        results = [r for r in results if r.chunk is not None]

        logger.info(
            f"Retrieved {len(results)} chunks",
            extra={"query": query, "channel_id": str(channel_id), "result_count": len(results)},
        )

        return results

    async def _expand_query(self, query: str) -> list[str]:
        """Expand query using Claude API.

        Generates additional related queries to improve recall.

        Args:
            query: Original query

        Returns:
            List of queries [original, expanded1, expanded2, ...]
        """
        if not self.llm_client:
            logger.warning("LLM client not configured, skipping query expansion")
            return [query]

        try:
            # Render prompt from centralized template
            prompt = self.prompt_manager.render(
                PromptType.QUERY_EXPANSION,
                query=query,
                num_expansions=self.query_config.num_expansions,
            )

            # Get LLM settings from template
            llm_settings = self.prompt_manager.get_llm_settings(PromptType.QUERY_EXPANSION)

            response = await self.llm_client.messages.create(
                model=llm_settings.model,
                max_tokens=llm_settings.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from response
            content_block = response.content[0]
            if not hasattr(content_block, "text"):
                raise ValueError(f"Unexpected content type: {type(content_block)}")

            expanded_text = content_block.text.strip()
            expanded_queries = [q.strip() for q in expanded_text.split("\n") if q.strip()]

            # Return original + expanded
            all_queries = [query] + expanded_queries[: self.query_config.num_expansions]
            logger.debug(f"Expanded query: {query} → {all_queries}")
            return all_queries

        except Exception as e:
            logger.warning(
                f"Query expansion failed, using original query only: {e}",
                exc_info=True,
            )
            return [query]

    async def _load_chunks(
        self,
        results: list[RetrievalResult],
        channel_id: uuid.UUID,
        content_types: list[str] | None = None,
        position: ChunkPosition | None = None,
        min_performance: float | None = None,
        is_opinion: bool | None = None,
        is_example: bool | None = None,
    ) -> None:
        """Load ContentChunk objects for results with optional filters.

        Modifies results in-place by setting chunk attribute.

        Args:
            results: List of RetrievalResult objects
            channel_id: Channel UUID
            content_types: Filter by content types
            position: Filter by chunk position
            min_performance: Minimum performance score
            is_opinion: Filter by opinion chunks
            is_example: Filter by example chunks
        """
        if not results:
            return

        chunk_ids = [r.chunk_id for r in results]

        async with self.db_session_factory() as session:
            # Build query with filters
            query = select(ContentChunk).where(
                and_(
                    ContentChunk.id.in_(chunk_ids),
                    ContentChunk.channel_id == channel_id,
                )
            )

            # Apply optional filters
            if content_types:
                query = query.where(ContentChunk.content_type.in_(content_types))
            if position:
                query = query.where(ContentChunk.position == position)
            if min_performance is not None:
                query = query.where(ContentChunk.performance_score >= min_performance)
            if is_opinion is not None:
                query = query.where(ContentChunk.is_opinion == is_opinion)
            if is_example is not None:
                query = query.where(ContentChunk.is_example == is_example)

            result = await session.execute(query)
            chunks = result.scalars().all()

            # Map chunks to results
            chunk_map = {chunk.id: chunk for chunk in chunks}
            for r in results:
                r.chunk = chunk_map.get(r.chunk_id)


class SpecializedRetriever(RAGRetriever):
    """Specialized retriever for opinions, examples, and hooks.

    Extends RAGRetriever with convenience methods for common retrieval patterns.
    """

    async def retrieve_opinions(
        self,
        topic: str,
        channel_id: uuid.UUID,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Retrieve opinion chunks related to topic.

        Args:
            topic: Topic query
            channel_id: Channel UUID
            top_k: Number of results

        Returns:
            List of opinion chunks sorted by relevance
        """
        logger.info(f"Retrieving opinions for topic: {topic}")
        return await self.retrieve(
            query=topic,
            channel_id=channel_id,
            top_k=top_k,
            is_opinion=True,
        )

    async def retrieve_examples(
        self,
        topic: str,
        channel_id: uuid.UUID,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Retrieve example chunks related to topic.

        Args:
            topic: Topic query
            channel_id: Channel UUID
            top_k: Number of results

        Returns:
            List of example chunks sorted by relevance
        """
        logger.info(f"Retrieving examples for topic: {topic}")
        return await self.retrieve(
            query=topic,
            channel_id=channel_id,
            top_k=top_k,
            is_example=True,
        )

    async def retrieve_hooks(
        self,
        topic: str,
        channel_id: uuid.UUID,
        top_k: int = 5,
        min_performance: float = 0.5,
    ) -> list[RetrievalResult]:
        """Retrieve high-quality hook chunks.

        Args:
            topic: Topic query
            channel_id: Channel UUID
            top_k: Number of results
            min_performance: Minimum performance score (default: 0.5)

        Returns:
            List of hook chunks sorted by relevance
        """
        logger.info(f"Retrieving hooks for topic: {topic} (min_performance={min_performance})")
        return await self.retrieve(
            query=topic,
            channel_id=channel_id,
            top_k=top_k,
            position=ChunkPosition.HOOK,
            min_performance=min_performance,
        )

    async def retrieve_high_performers(
        self,
        topic: str,
        channel_id: uuid.UUID,
        top_k: int = 5,
        min_performance: float = 0.7,
    ) -> list[RetrievalResult]:
        """Retrieve high-performing chunks.

        Args:
            topic: Topic query
            channel_id: Channel UUID
            top_k: Number of results
            min_performance: Minimum performance score (default: 0.7)

        Returns:
            List of high-performing chunks sorted by relevance
        """
        logger.info(
            f"Retrieving high performers for topic: {topic} (min_performance={min_performance})"
        )
        return await self.retrieve(
            query=topic,
            channel_id=channel_id,
            top_k=top_k,
            min_performance=min_performance,
        )


__all__ = [
    "RetrievalResult",
    "RAGRetriever",
    "SpecializedRetriever",
]
