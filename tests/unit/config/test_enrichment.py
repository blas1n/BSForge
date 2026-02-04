"""Unit tests for enrichment configuration models."""

import pytest
from pydantic import ValidationError

from app.config.enrichment import (
    ClusterEnrichmentConfig,
    EnrichmentConfig,
)
from app.config.rag import GenerationConfig
from app.config.research import ResearchConfig


class TestClusterEnrichmentConfig:
    """Tests for ClusterEnrichmentConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ClusterEnrichmentConfig()
        assert config.enabled is True
        assert config.min_cluster_size == 1
        assert config.generate_summary is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ClusterEnrichmentConfig(
            enabled=False,
            min_cluster_size=3,
            generate_summary=False,
        )
        assert config.enabled is False
        assert config.min_cluster_size == 3
        assert config.generate_summary is False

    def test_min_cluster_size_range(self):
        """Test min_cluster_size validation."""
        config = ClusterEnrichmentConfig(min_cluster_size=1)
        assert config.min_cluster_size == 1

        config = ClusterEnrichmentConfig(min_cluster_size=10)
        assert config.min_cluster_size == 10

        with pytest.raises(ValidationError):
            ClusterEnrichmentConfig(min_cluster_size=0)

        with pytest.raises(ValidationError):
            ClusterEnrichmentConfig(min_cluster_size=11)


class TestEnrichmentConfig:
    """Tests for EnrichmentConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = EnrichmentConfig()
        assert isinstance(config.cluster, ClusterEnrichmentConfig)
        assert isinstance(config.research, ResearchConfig)
        assert isinstance(config.generation, GenerationConfig)

    def test_default_subconfig_values(self):
        """Test default sub-configuration values."""
        config = EnrichmentConfig()
        # Cluster defaults
        assert config.cluster.enabled is True
        assert config.cluster.min_cluster_size == 1
        # Research defaults
        assert config.research.enabled is True
        assert config.research.max_queries == 3
        # Generation defaults
        assert config.generation.format == "shorts"
        assert config.generation.temperature == 0.7

    def test_custom_subconfigs(self):
        """Test custom sub-configurations."""
        config = EnrichmentConfig(
            cluster=ClusterEnrichmentConfig(min_cluster_size=5),
            research=ResearchConfig(max_queries=5),
            generation=GenerationConfig(temperature=0.5),
        )
        assert config.cluster.min_cluster_size == 5
        assert config.research.max_queries == 5
        assert config.generation.temperature == 0.5

    def test_nested_validation(self):
        """Test that nested config validation works."""
        # This should fail because temperature is out of range
        with pytest.raises(ValidationError):
            EnrichmentConfig(generation=GenerationConfig(temperature=2.0))

        # This should fail because min_cluster_size is out of range
        with pytest.raises(ValidationError):
            EnrichmentConfig(cluster=ClusterEnrichmentConfig(min_cluster_size=0))

    def test_partial_override(self):
        """Test partial override of sub-configurations."""
        config = EnrichmentConfig(
            cluster=ClusterEnrichmentConfig(enabled=False),
        )
        # Cluster is overridden
        assert config.cluster.enabled is False
        # Research keeps defaults
        assert config.research.enabled is True
        # Generation keeps defaults
        assert config.generation.format == "shorts"
