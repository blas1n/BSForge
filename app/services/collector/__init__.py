"""Topic collection services.

This package implements the topic collection pipeline:
1. Source collectors fetch raw topics from external sources
2. Normalizer translates, cleans, and classifies topics
3. Deduplicator removes duplicate topics
4. Scorer calculates relevance scores
5. Queue manager adds topics to priority queue
"""

from app.config import DedupConfig, QueueConfig, ScoringConfig, ScoringWeights
from app.services.collector.base import (
    BaseSource,
    CollectionResult,
    NormalizedTopic,
    RawTopic,
    ScoredTopic,
)
from app.services.collector.deduplicator import (
    DedupReason,
    DedupResult,
    TopicDeduplicator,
)
from app.services.collector.normalizer import ClassificationResult, TopicNormalizer
from app.services.collector.queue_manager import QueueStats, TopicQueueManager
from app.services.collector.scorer import ScoreComponents, TopicScorer

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
    # Deduplicator
    "TopicDeduplicator",
    "DedupConfig",
    "DedupResult",
    "DedupReason",
    # Scorer
    "TopicScorer",
    "ScoringConfig",
    "ScoringWeights",
    "ScoreComponents",
    # Queue Manager
    "TopicQueueManager",
    "QueueConfig",
    "QueueStats",
]
