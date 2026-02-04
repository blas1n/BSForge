"""Unit tests for RAG configuration models."""

import pytest
from pydantic import ValidationError

from app.config.rag import (
    ChunkingConfig,
    EmbeddingConfig,
    GenerationConfig,
    QualityCheckConfig,
    QueryExpansionConfig,
    RAGConfig,
    RetrievalConfig,
)


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = EmbeddingConfig()
        assert config.model_name == "BAAI/bge-m3"
        assert config.model_revision is None
        assert config.dimensions == 1024
        assert config.batch_size == 32
        assert config.device == "cpu"
        assert config.normalize_embeddings is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = EmbeddingConfig(
            model_name="custom/model",
            dimensions=512,
            batch_size=64,
            device="cuda",
            normalize_embeddings=False,
        )
        assert config.model_name == "custom/model"
        assert config.dimensions == 512
        assert config.batch_size == 64
        assert config.device == "cuda"
        assert config.normalize_embeddings is False

    def test_dimensions_range(self):
        """Test dimensions validation."""
        config = EmbeddingConfig(dimensions=128)
        assert config.dimensions == 128

        config = EmbeddingConfig(dimensions=4096)
        assert config.dimensions == 4096

        with pytest.raises(ValidationError):
            EmbeddingConfig(dimensions=127)

        with pytest.raises(ValidationError):
            EmbeddingConfig(dimensions=4097)

    def test_batch_size_range(self):
        """Test batch size validation."""
        config = EmbeddingConfig(batch_size=1)
        assert config.batch_size == 1

        config = EmbeddingConfig(batch_size=128)
        assert config.batch_size == 128

        with pytest.raises(ValidationError):
            EmbeddingConfig(batch_size=0)

        with pytest.raises(ValidationError):
            EmbeddingConfig(batch_size=129)

    def test_device_options(self):
        """Test device validation."""
        for device in ["cpu", "cuda", "mps"]:
            config = EmbeddingConfig(device=device)
            assert config.device == device

        with pytest.raises(ValidationError):
            EmbeddingConfig(device="invalid")


class TestRetrievalConfig:
    """Tests for RetrievalConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetrievalConfig()
        assert config.semantic_weight == 0.7
        assert config.keyword_weight == 0.3
        assert config.semantic_top_k == 20
        assert config.keyword_top_k == 20
        assert config.final_top_k == 5
        assert config.enable_reranking is True
        assert config.reranker_model == "BAAI/bge-reranker-base"
        assert config.enable_mmr is True
        assert config.mmr_lambda == 0.7
        assert config.min_similarity == 0.0

    def test_weight_ranges(self):
        """Test weight validation."""
        config = RetrievalConfig(semantic_weight=0.0, keyword_weight=1.0)
        assert config.semantic_weight == 0.0
        assert config.keyword_weight == 1.0

        with pytest.raises(ValidationError):
            RetrievalConfig(semantic_weight=-0.1)

        with pytest.raises(ValidationError):
            RetrievalConfig(semantic_weight=1.1)

    def test_top_k_ranges(self):
        """Test top_k validation."""
        config = RetrievalConfig(semantic_top_k=1, keyword_top_k=100, final_top_k=1)
        assert config.semantic_top_k == 1
        assert config.keyword_top_k == 100
        assert config.final_top_k == 1

        with pytest.raises(ValidationError):
            RetrievalConfig(semantic_top_k=0)

        with pytest.raises(ValidationError):
            RetrievalConfig(final_top_k=21)


class TestQueryExpansionConfig:
    """Tests for QueryExpansionConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = QueryExpansionConfig()
        assert config.enabled is True
        assert config.num_expansions == 2
        assert config.model == "claude-3-5-haiku-20241022"
        assert config.max_tokens == 100

    def test_num_expansions_range(self):
        """Test num_expansions validation."""
        config = QueryExpansionConfig(num_expansions=1)
        assert config.num_expansions == 1

        config = QueryExpansionConfig(num_expansions=5)
        assert config.num_expansions == 5

        with pytest.raises(ValidationError):
            QueryExpansionConfig(num_expansions=0)

        with pytest.raises(ValidationError):
            QueryExpansionConfig(num_expansions=6)

    def test_max_tokens_range(self):
        """Test max_tokens validation."""
        config = QueryExpansionConfig(max_tokens=50)
        assert config.max_tokens == 50

        config = QueryExpansionConfig(max_tokens=500)
        assert config.max_tokens == 500

        with pytest.raises(ValidationError):
            QueryExpansionConfig(max_tokens=49)

        with pytest.raises(ValidationError):
            QueryExpansionConfig(max_tokens=501)


class TestChunkingConfig:
    """Tests for ChunkingConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ChunkingConfig()
        assert config.strategy == "structure"
        assert config.max_chunk_tokens == 200
        assert config.overlap_tokens == 20
        assert config.preserve_structure is True
        assert config.use_llm_classification is False
        assert len(config.opinion_patterns) > 0
        assert len(config.example_patterns) > 0
        assert len(config.analogy_patterns) > 0

    def test_strategy_options(self):
        """Test strategy validation."""
        for strategy in ["structure", "fixed", "semantic"]:
            config = ChunkingConfig(strategy=strategy)
            assert config.strategy == strategy

        with pytest.raises(ValidationError):
            ChunkingConfig(strategy="invalid")

    def test_chunk_token_ranges(self):
        """Test chunk token validation."""
        config = ChunkingConfig(max_chunk_tokens=50, overlap_tokens=0)
        assert config.max_chunk_tokens == 50
        assert config.overlap_tokens == 0

        config = ChunkingConfig(max_chunk_tokens=1000, overlap_tokens=100)
        assert config.max_chunk_tokens == 1000
        assert config.overlap_tokens == 100

        with pytest.raises(ValidationError):
            ChunkingConfig(max_chunk_tokens=49)

        with pytest.raises(ValidationError):
            ChunkingConfig(overlap_tokens=101)

    def test_custom_patterns(self):
        """Test custom patterns configuration."""
        config = ChunkingConfig(
            opinion_patterns=["custom pattern"],
            example_patterns=["another pattern"],
        )
        assert config.opinion_patterns == ["custom pattern"]
        assert config.example_patterns == ["another pattern"]


class TestQualityCheckConfig:
    """Tests for QualityCheckConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = QualityCheckConfig()
        assert config.min_style_score == 0.7
        assert config.min_hook_score == 0.5
        assert config.max_forbidden_words == 2
        assert config.max_duration == 65
        assert config.min_duration == 20

    def test_score_ranges(self):
        """Test score validation."""
        config = QualityCheckConfig(min_style_score=0.0, min_hook_score=1.0)
        assert config.min_style_score == 0.0
        assert config.min_hook_score == 1.0

        with pytest.raises(ValidationError):
            QualityCheckConfig(min_style_score=-0.1)

        with pytest.raises(ValidationError):
            QualityCheckConfig(min_hook_score=1.1)

    def test_duration_ranges(self):
        """Test duration validation."""
        config = QualityCheckConfig(min_duration=15, max_duration=600)
        assert config.min_duration == 15
        assert config.max_duration == 600

        with pytest.raises(ValidationError):
            QualityCheckConfig(min_duration=14)

        with pytest.raises(ValidationError):
            QualityCheckConfig(max_duration=601)


class TestGenerationConfig:
    """Tests for GenerationConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = GenerationConfig()
        assert config.format == "shorts"
        assert config.target_duration == 55
        assert config.style == "informative"
        assert config.model == "claude-3-5-sonnet-20241022"
        assert config.temperature == 0.7
        assert config.max_tokens == 2000
        assert config.retry_on_failure is True
        assert config.max_retries == 2

    def test_format_options(self):
        """Test format validation."""
        config = GenerationConfig(format="shorts")
        assert config.format == "shorts"

        config = GenerationConfig(format="long")
        assert config.format == "long"

        with pytest.raises(ValidationError):
            GenerationConfig(format="invalid")

    def test_style_options(self):
        """Test style validation."""
        for style in ["informative", "opinion", "reaction", "tutorial"]:
            config = GenerationConfig(style=style)
            assert config.style == style

        with pytest.raises(ValidationError):
            GenerationConfig(style="invalid")

    def test_temperature_range(self):
        """Test temperature validation."""
        config = GenerationConfig(temperature=0.0)
        assert config.temperature == 0.0

        config = GenerationConfig(temperature=1.0)
        assert config.temperature == 1.0

        with pytest.raises(ValidationError):
            GenerationConfig(temperature=-0.1)

        with pytest.raises(ValidationError):
            GenerationConfig(temperature=1.1)

    def test_token_range(self):
        """Test max_tokens validation."""
        config = GenerationConfig(max_tokens=500)
        assert config.max_tokens == 500

        config = GenerationConfig(max_tokens=4000)
        assert config.max_tokens == 4000

        with pytest.raises(ValidationError):
            GenerationConfig(max_tokens=499)

        with pytest.raises(ValidationError):
            GenerationConfig(max_tokens=4001)


class TestRAGConfig:
    """Tests for complete RAGConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RAGConfig()
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.retrieval, RetrievalConfig)
        assert isinstance(config.query_expansion, QueryExpansionConfig)
        assert isinstance(config.chunking, ChunkingConfig)
        assert isinstance(config.quality_check, QualityCheckConfig)
        assert isinstance(config.generation, GenerationConfig)

    def test_custom_subconfigs(self):
        """Test with custom sub-configurations."""
        config = RAGConfig(
            embedding=EmbeddingConfig(dimensions=512),
            retrieval=RetrievalConfig(semantic_weight=0.8),
            generation=GenerationConfig(temperature=0.5),
        )
        assert config.embedding.dimensions == 512
        assert config.retrieval.semantic_weight == 0.8
        assert config.generation.temperature == 0.5
