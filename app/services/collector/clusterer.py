"""Topic clustering service.

Groups similar topics from multiple sources based on title/keyword similarity.
Provides aggregated information for richer script generation.
"""

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.collector.base import ScoredTopic

logger = get_logger(__name__)


@dataclass
class TopicCluster:
    """A cluster of related topics from multiple sources.

    Attributes:
        primary_topic: The highest-scored topic in the cluster
        related_topics: Other topics in the cluster
        sources: Set of source names that covered this topic
        combined_keywords: Merged keywords from all topics
        combined_categories: Merged categories from all topics
        total_engagement: Sum of engagement metrics across sources
        coverage_score: How many sources covered this topic (0-1)
    """

    primary_topic: ScoredTopic
    related_topics: list[ScoredTopic] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    combined_keywords: list[str] = field(default_factory=list)
    combined_categories: list[str] = field(default_factory=list)
    total_engagement: int = 0
    coverage_score: float = 0.0

    @property
    def all_topics(self) -> list[ScoredTopic]:
        """Get all topics in this cluster."""
        return [self.primary_topic] + self.related_topics

    @property
    def topic_count(self) -> int:
        """Get total number of topics in cluster."""
        return len(self.all_topics)

    @property
    def source_count(self) -> int:
        """Get number of unique sources."""
        return len(self.sources)

    def get_all_titles(self) -> list[str]:
        """Get all original titles from topics in cluster."""
        return [t.title_original for t in self.all_topics]

    def get_all_urls(self) -> list[str]:
        """Get all source URLs from topics in cluster."""
        return [str(t.source_url) for t in self.all_topics]

    def get_summary_info(self) -> dict:
        """Get summary information for script generation."""
        return {
            "primary_title": self.primary_topic.title_original,
            "primary_normalized": self.primary_topic.title_normalized,
            "source_count": self.source_count,
            "sources": list(self.sources),
            "all_titles": self.get_all_titles(),
            "keywords": self.combined_keywords,
            "categories": self.combined_categories,
            "total_engagement": self.total_engagement,
            "coverage_score": self.coverage_score,
        }


class TopicClusterer:
    """Clusters similar topics based on keyword and title similarity.

    Uses Jaccard similarity on keywords and n-gram similarity on titles
    to group related topics from different sources.
    """

    def __init__(
        self,
        keyword_weight: float = 0.6,
        title_weight: float = 0.4,
        similarity_threshold: float = 0.3,
        min_keyword_overlap: int = 2,
    ):
        """Initialize clusterer with similarity parameters.

        Args:
            keyword_weight: Weight for keyword similarity (0-1)
            title_weight: Weight for title similarity (0-1)
            similarity_threshold: Minimum similarity to cluster (0-1)
            min_keyword_overlap: Minimum keyword overlap count
        """
        self.keyword_weight = keyword_weight
        self.title_weight = title_weight
        self.similarity_threshold = similarity_threshold
        self.min_keyword_overlap = min_keyword_overlap

    def cluster(
        self,
        topics: list[ScoredTopic],
        total_sources: int | None = None,
    ) -> list[TopicCluster]:
        """Cluster similar topics together.

        Args:
            topics: List of scored topics to cluster
            total_sources: Total number of sources for coverage calculation

        Returns:
            List of topic clusters, sorted by score
        """
        if not topics:
            return []

        # Sort by score descending
        sorted_topics = sorted(topics, key=lambda t: t.score_total, reverse=True)

        clusters: list[TopicCluster] = []
        clustered_indices: set[int] = set()

        for i, topic in enumerate(sorted_topics):
            if i in clustered_indices:
                continue

            # Start new cluster with this topic
            cluster = self._create_cluster(topic, total_sources)
            clustered_indices.add(i)

            # Find similar topics
            for j, other in enumerate(sorted_topics):
                if j in clustered_indices:
                    continue

                similarity = self._calculate_similarity(topic, other)
                if similarity >= self.similarity_threshold:
                    self._add_to_cluster(cluster, other)
                    clustered_indices.add(j)

            clusters.append(cluster)

        # Sort clusters by primary topic score
        clusters.sort(key=lambda c: c.primary_topic.score_total, reverse=True)

        logger.info(
            "Topic clustering complete",
            total_topics=len(topics),
            cluster_count=len(clusters),
            multi_source_clusters=sum(1 for c in clusters if c.source_count > 1),
        )

        return clusters

    def _create_cluster(
        self,
        topic: ScoredTopic,
        total_sources: int | None,
    ) -> TopicCluster:
        """Create a new cluster from a topic.

        Args:
            topic: Primary topic for the cluster
            total_sources: Total number of sources

        Returns:
            New TopicCluster
        """
        source_name = topic.metrics.get("metadata", {}).get("source_name", "unknown")
        if not source_name or source_name == "unknown":
            # Try to extract from source_id or URL
            source_name = self._extract_source_name(topic)

        engagement = self._calculate_engagement(topic)

        cluster = TopicCluster(
            primary_topic=topic,
            sources={source_name},
            combined_keywords=list(topic.keywords),
            combined_categories=list(topic.categories),
            total_engagement=engagement,
        )

        if total_sources:
            cluster.coverage_score = 1 / total_sources

        return cluster

    def _add_to_cluster(self, cluster: TopicCluster, topic: ScoredTopic) -> None:
        """Add a topic to an existing cluster.

        Args:
            cluster: Cluster to add to
            topic: Topic to add
        """
        cluster.related_topics.append(topic)

        # Add source
        source_name = topic.metrics.get("metadata", {}).get("source_name", "unknown")
        if not source_name or source_name == "unknown":
            source_name = self._extract_source_name(topic)
        cluster.sources.add(source_name)

        # Merge keywords (deduplicated)
        for kw in topic.keywords:
            if kw not in cluster.combined_keywords:
                cluster.combined_keywords.append(kw)

        # Merge categories (deduplicated)
        for cat in topic.categories:
            if cat not in cluster.combined_categories:
                cluster.combined_categories.append(cat)

        # Update engagement
        cluster.total_engagement += self._calculate_engagement(topic)

        # Update coverage score
        cluster.coverage_score = len(cluster.sources) / max(len(cluster.sources), 1)

    def _calculate_similarity(
        self,
        topic1: ScoredTopic,
        topic2: ScoredTopic,
    ) -> float:
        """Calculate similarity between two topics.

        Uses weighted combination of keyword and title similarity.

        Args:
            topic1: First topic
            topic2: Second topic

        Returns:
            Similarity score (0-1)
        """
        # Keyword similarity (Jaccard)
        kw1 = set(topic1.keywords)
        kw2 = set(topic2.keywords)

        if kw1 and kw2:
            keyword_overlap = len(kw1 & kw2)
            keyword_jaccard = keyword_overlap / len(kw1 | kw2)

            # Require minimum keyword overlap
            if keyword_overlap < self.min_keyword_overlap:
                keyword_jaccard *= 0.5  # Penalize low overlap
        else:
            keyword_jaccard = 0.0

        # Title similarity (n-gram based)
        title_sim = self._title_similarity(
            topic1.title_normalized,
            topic2.title_normalized,
        )

        # Category bonus
        cat_overlap = len(set(topic1.categories) & set(topic2.categories))
        category_bonus = min(cat_overlap * 0.1, 0.2)

        # Combined similarity
        combined = (
            self.keyword_weight * keyword_jaccard + self.title_weight * title_sim + category_bonus
        )

        return min(combined, 1.0)

    def _title_similarity(self, title1: str, title2: str, n: int = 2) -> float:
        """Calculate n-gram similarity between titles.

        Args:
            title1: First title (normalized)
            title2: Second title (normalized)
            n: N-gram size

        Returns:
            Similarity score (0-1)
        """
        # Clean and tokenize
        words1 = self._tokenize(title1)
        words2 = self._tokenize(title2)

        if not words1 or not words2:
            return 0.0

        # Generate n-grams
        ngrams1 = set(self._get_ngrams(words1, n))
        ngrams2 = set(self._get_ngrams(words2, n))

        if not ngrams1 or not ngrams2:
            # Fall back to word overlap
            word_overlap = len(set(words1) & set(words2))
            return word_overlap / max(len(set(words1) | set(words2)), 1)

        # Jaccard similarity on n-grams
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)

        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Args:
            text: Text to tokenize

        Returns:
            List of word tokens
        """
        # Remove special characters but keep Korean/English/numbers
        text = re.sub(r"[^\w\s가-힣]", " ", text)
        # Split and filter empty
        return [w.strip() for w in text.lower().split() if w.strip()]

    def _get_ngrams(self, words: list[str], n: int) -> list[tuple[str, ...]]:
        """Generate n-grams from word list.

        Args:
            words: List of words
            n: N-gram size

        Returns:
            List of n-gram tuples
        """
        if len(words) < n:
            return [tuple(words)]
        return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]

    def _calculate_engagement(self, topic: ScoredTopic) -> int:
        """Calculate total engagement for a topic.

        Args:
            topic: Topic to calculate engagement for

        Returns:
            Total engagement score
        """
        metrics = topic.metrics
        engagement = 0

        # Common metric names
        engagement += metrics.get("score", 0)
        engagement += metrics.get("upvotes", 0)
        engagement += metrics.get("views", 0) // 100  # Normalize views
        engagement += metrics.get("recommends", 0)
        engagement += metrics.get("comments", 0) * 2  # Comments are valuable

        return engagement

    def _extract_source_name(self, topic: ScoredTopic) -> str:
        """Extract source name from topic.

        Args:
            topic: Topic to extract source from

        Returns:
            Source name string
        """
        url = str(topic.source_url).lower()

        # Known sources
        source_patterns = {
            "reddit.com": "Reddit",
            "news.ycombinator.com": "HackerNews",
            "dcinside.com": "디시인사이드",
            "clien.net": "클리앙",
            "ruliweb.com": "루리웹",
            "fmkorea.com": "FM코리아",
            "sbs.co.kr": "SBS",
            "khan.co.kr": "경향신문",
        }

        for pattern, name in source_patterns.items():
            if pattern in url:
                return name

        return "unknown"


def cluster_topics(
    topics: list[ScoredTopic],
    similarity_threshold: float = 0.3,
    total_sources: int | None = None,
) -> list[TopicCluster]:
    """Convenience function to cluster topics.

    Args:
        topics: List of scored topics
        similarity_threshold: Minimum similarity to cluster
        total_sources: Total number of sources for coverage calculation

    Returns:
        List of topic clusters
    """
    clusterer = TopicClusterer(similarity_threshold=similarity_threshold)
    return clusterer.cluster(topics, total_sources)


def get_top_clusters(
    clusters: list[TopicCluster],
    min_sources: int = 1,
    limit: int = 5,
) -> list[TopicCluster]:
    """Get top clusters filtered by minimum source count.

    Args:
        clusters: List of topic clusters
        min_sources: Minimum number of sources required
        limit: Maximum clusters to return

    Returns:
        Filtered and limited list of clusters
    """
    filtered = [c for c in clusters if c.source_count >= min_sources]

    # Sort by: multi-source first, then by score
    filtered.sort(
        key=lambda c: (c.source_count > 1, c.primary_topic.score_total),
        reverse=True,
    )

    return filtered[:limit]


__all__ = [
    "TopicCluster",
    "TopicClusterer",
    "cluster_topics",
    "get_top_clusters",
]
