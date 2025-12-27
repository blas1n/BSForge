"""Pipeline services package.

This package provides orchestration pipelines for complex multi-step workflows.
"""

from app.services.pipeline.enriched_generation import EnrichedGenerationPipeline

__all__ = ["EnrichedGenerationPipeline"]
