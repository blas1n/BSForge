"""RAG Facade for simplified dependency management.

This module provides a facade that groups related RAG dependencies together,
reducing the number of constructor parameters needed by services like ScriptGenerator.

Example:
    # Before (10 dependencies):
    generator = ScriptGenerator(
        context_builder, prompt_builder, chunker, embedder,
        vector_db, llm_client, prompt_manager, db_session_factory,
        config, quality_config
    )

    # After (3 dependencies):
    generator = ScriptGenerator(
        rag_facade=RAGFacade(...),
        db_session_factory=factory,
        config=config,
    )
"""

from dataclasses import dataclass

from app.config.rag import EmbeddingConfig, QualityCheckConfig, RetrievalConfig
from app.infrastructure.bm25_search import BM25Search
from app.infrastructure.llm import LLMClient
from app.infrastructure.pgvector_db import PgVectorDB
from app.prompts.manager import PromptManager
from app.services.rag.chunker import ScriptChunker
from app.services.rag.context import ContextBuilder
from app.services.rag.embedder import ContentEmbedder
from app.services.rag.prompt import PromptBuilder
from app.services.rag.quality import ScriptQualityChecker
from app.services.rag.reranker import RAGReranker
from app.services.rag.retriever import SpecializedRetriever


@dataclass
class RAGFacade:
    """Facade for RAG-related services.

    Groups together the retrieval, embedding, and generation components
    used throughout the RAG pipeline.

    Attributes:
        retriever: Specialized retriever for hybrid search
        embedder: Content embedder for vector operations
        context_builder: Context builder for assembling prompts
        prompt_builder: Prompt builder for template rendering
        chunker: Script chunker for splitting content
        quality_checker: Quality checker for script validation
        llm_client: LLM client for generation
        prompt_manager: Prompt template manager
    """

    retriever: SpecializedRetriever
    embedder: ContentEmbedder
    context_builder: ContextBuilder
    prompt_builder: PromptBuilder
    chunker: ScriptChunker
    quality_checker: ScriptQualityChecker
    llm_client: LLMClient
    prompt_manager: PromptManager

    @classmethod
    def create(
        cls,
        vector_db: PgVectorDB,
        bm25_search: BM25Search,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        retrieval_config: RetrievalConfig | None = None,
        embedding_config: EmbeddingConfig | None = None,
        quality_config: QualityCheckConfig | None = None,
    ) -> "RAGFacade":
        """Factory method to create RAGFacade with all components.

        This is the recommended way to create a RAGFacade as it properly
        initializes all internal components with appropriate configurations.

        Args:
            vector_db: Vector database for semantic search
            bm25_search: BM25 search for keyword matching
            llm_client: LLM client for reranking and generation
            prompt_manager: Prompt template manager
            retrieval_config: Configuration for retrieval
            embedding_config: Configuration for embedding
            quality_config: Configuration for quality checking

        Returns:
            Configured RAGFacade instance
        """
        retrieval_config = retrieval_config or RetrievalConfig()
        embedding_config = embedding_config or EmbeddingConfig()
        quality_config = quality_config or QualityCheckConfig()

        # Create reranker for retrieval
        reranker = RAGReranker(
            llm_client=llm_client,
            prompt_manager=prompt_manager,
            config=retrieval_config,
        )

        # Create retriever
        retriever = SpecializedRetriever(
            vector_db=vector_db,
            bm25_search=bm25_search,
            reranker=reranker,
            config=retrieval_config,
        )

        # Create embedder
        embedder = ContentEmbedder(
            vector_db=vector_db,
            config=embedding_config,
        )

        # Create context builder
        context_builder = ContextBuilder(
            retriever=retriever,
            llm_client=llm_client,
            config=retrieval_config,
        )

        # Create prompt builder
        prompt_builder = PromptBuilder(
            prompt_manager=prompt_manager,
        )

        # Create chunker
        chunker = ScriptChunker(
            llm_client=llm_client,
        )

        # Create quality checker
        quality_checker = ScriptQualityChecker(
            config=quality_config,
        )

        return cls(
            retriever=retriever,
            embedder=embedder,
            context_builder=context_builder,
            prompt_builder=prompt_builder,
            chunker=chunker,
            quality_checker=quality_checker,
            llm_client=llm_client,
            prompt_manager=prompt_manager,
        )

    @property
    def vector_db(self) -> PgVectorDB:
        """Get the vector database from embedder."""
        return self.embedder.vector_db
