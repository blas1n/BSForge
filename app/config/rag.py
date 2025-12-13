"""RAG system configuration models.

This module provides typed Pydantic configuration for all RAG components:
- Embedding (BGE-M3)
- Retrieval (Hybrid search)
- Query expansion
- Chunking
- Quality checks
- Script generation
"""

from typing import Literal

from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    """Embedding model configuration.

    Attributes:
        model_name: HuggingFace model identifier
        model_revision: Model version/revision
        dimensions: Embedding dimension
        batch_size: Batch size for encoding
        device: Device to use (cpu, cuda, mps)
        normalize_embeddings: Whether to L2 normalize embeddings
    """

    model_name: str = Field(default="BAAI/bge-m3", description="HuggingFace model identifier")
    model_revision: str | None = Field(default=None, description="Model revision")
    dimensions: int = Field(default=1024, ge=128, le=4096, description="Embedding dimension")
    batch_size: int = Field(default=32, ge=1, le=128, description="Batch size")
    device: Literal["cpu", "cuda", "mps"] = Field(default="cpu", description="Device")
    normalize_embeddings: bool = Field(default=True, description="Normalize embeddings")


class RetrievalConfig(BaseModel):
    """Retrieval configuration.

    Attributes:
        semantic_weight: Weight for semantic search (0-1)
        keyword_weight: Weight for BM25 keyword search (0-1)
        semantic_top_k: Number of semantic results
        keyword_top_k: Number of keyword results
        final_top_k: Final number of results after reranking
        enable_reranking: Whether to use reranker
        reranker_model: Reranker model name
        enable_mmr: Whether to apply MMR for diversity
        mmr_lambda: MMR lambda (relevance vs diversity)
        min_similarity: Minimum similarity threshold
    """

    semantic_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    semantic_top_k: int = Field(default=20, ge=1, le=100)
    keyword_top_k: int = Field(default=20, ge=1, le=100)
    final_top_k: int = Field(default=5, ge=1, le=20)
    enable_reranking: bool = Field(default=True)
    reranker_model: str = Field(default="BAAI/bge-reranker-base")
    enable_mmr: bool = Field(default=True)
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)


class QueryExpansionConfig(BaseModel):
    """Query expansion configuration.

    Attributes:
        enabled: Whether to expand queries
        num_expansions: Number of expansion queries
        model: LLM model for expansion
        max_tokens: Max tokens for expansion
    """

    enabled: bool = Field(default=True)
    num_expansions: int = Field(default=2, ge=1, le=5)
    model: str = Field(default="claude-3-5-haiku-20241022")
    max_tokens: int = Field(default=100, ge=50, le=500)


class ChunkingConfig(BaseModel):
    """Content chunking configuration.

    Attributes:
        strategy: Chunking strategy
        max_chunk_tokens: Maximum tokens per chunk
        overlap_tokens: Overlap between chunks
        preserve_structure: Whether to preserve structural boundaries
    """

    strategy: Literal["structure", "fixed", "semantic"] = Field(default="structure")
    max_chunk_tokens: int = Field(default=200, ge=50, le=1000)
    overlap_tokens: int = Field(default=20, ge=0, le=100)
    preserve_structure: bool = Field(default=True)


class QualityCheckConfig(BaseModel):
    """Script quality check configuration.

    Attributes:
        min_style_score: Minimum style consistency score
        min_hook_score: Minimum hook quality score
        max_forbidden_words: Maximum allowed forbidden words
        max_duration: Maximum duration in seconds
        min_duration: Minimum duration in seconds
    """

    min_style_score: float = Field(default=0.7, ge=0.0, le=1.0)
    min_hook_score: float = Field(default=0.5, ge=0.0, le=1.0)
    max_forbidden_words: int = Field(default=2, ge=0, le=10)
    max_duration: int = Field(default=65, ge=30, le=600)
    min_duration: int = Field(default=40, ge=15, le=300)


class GenerationConfig(BaseModel):
    """Script generation configuration.

    Attributes:
        format: Video format
        target_duration: Target duration in seconds
        style: Content style
        model: LLM model for generation
        temperature: Generation temperature
        max_tokens: Maximum tokens to generate
        retry_on_failure: Whether to retry on quality failure
        max_retries: Maximum retry attempts
    """

    format: Literal["shorts", "long"] = Field(default="shorts")
    target_duration: int = Field(default=55, ge=15, le=600)
    style: Literal["informative", "opinion", "reaction", "tutorial"] = Field(default="informative")
    model: str = Field(default="claude-3-5-sonnet-20241022")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, ge=500, le=4000)
    retry_on_failure: bool = Field(default=True)
    max_retries: int = Field(default=2, ge=0, le=5)


class RAGConfig(BaseModel):
    """Complete RAG system configuration.

    All sub-configs have defaults and can be used without explicit configuration.

    Attributes:
        embedding: Embedding model configuration
        retrieval: Retrieval configuration
        query_expansion: Query expansion configuration
        chunking: Content chunking configuration
        quality_check: Quality check configuration
        generation: Script generation configuration
    """

    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    query_expansion: QueryExpansionConfig = Field(default_factory=QueryExpansionConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    quality_check: QualityCheckConfig = Field(default_factory=QualityCheckConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


__all__ = [
    "RAGConfig",
    "EmbeddingConfig",
    "RetrievalConfig",
    "QueryExpansionConfig",
    "ChunkingConfig",
    "QualityCheckConfig",
    "GenerationConfig",
]
