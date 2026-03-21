"""Topic collection services.

This package implements the topic collection pipeline:
1. Source collectors fetch raw topics from external sources
2. Normalizer translates, cleans, and classifies topics
3. Filter applies include/exclude rules
4. Deduplication via DB hash check
"""

from app.services.collector.base import (
    BaseSource,
    CollectionResult,
    NormalizedTopic,
    RawTopic,
    ScoredTopic,
)
from app.services.collector.filter import FilterReason, FilterResult, TopicFilter
from app.services.collector.normalizer import ClassificationResult, TopicNormalizer

__all__ = [
    # Base DTOs
    "RawTopic",
    "NormalizedTopic",
    "ScoredTopic",
    "BaseSource",
    "CollectionResult",
    # Normalizer
    "TopicNormalizer",
    "ClassificationResult",
    # Filter
    "TopicFilter",
    "FilterResult",
    "FilterReason",
]
