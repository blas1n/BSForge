"""Enrichment pipeline configuration models.

This module provides configuration for the enriched generation pipeline
that combines cluster content integration with web research.
"""

from pydantic import BaseModel, Field

from app.config.rag import GenerationConfig
from app.config.research import ResearchConfig


class ClusterEnrichmentConfig(BaseModel):
    """Cluster content enrichment configuration.

    Attributes:
        enabled: Whether cluster enrichment is enabled
        min_cluster_size: Minimum topics in cluster to trigger enrichment
        generate_summary: Whether to generate LLM summary
    """

    enabled: bool = Field(default=True, description="Enable cluster enrichment")
    min_cluster_size: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Minimum topics in cluster to enrich",
    )
    generate_summary: bool = Field(
        default=True,
        description="Generate LLM-based unified summary",
    )


class EnrichmentConfig(BaseModel):
    """Complete enrichment pipeline configuration.

    Attributes:
        cluster: Cluster enrichment settings
        research: Web research settings
        generation: Script generation settings
    """

    cluster: ClusterEnrichmentConfig = Field(default_factory=ClusterEnrichmentConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


__all__ = [
    "ClusterEnrichmentConfig",
    "EnrichmentConfig",
]
