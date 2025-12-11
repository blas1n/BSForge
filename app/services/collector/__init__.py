"""Topic collection services.

This package implements the topic collection pipeline:
1. Source collectors fetch raw topics from external sources
2. Normalizer translates, cleans, and classifies topics
3. Deduplicator removes duplicate topics
4. Scorer calculates relevance scores
5. Queue manager adds topics to priority queue
"""
