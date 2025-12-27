"""Unit tests for topic clusterer."""

import uuid
from datetime import UTC, datetime

from app.services.collector.base import ScoredTopic
from app.services.collector.clusterer import (
    TopicCluster,
    TopicClusterer,
    cluster_topics,
    get_top_clusters,
    select_best_cluster,
)


def make_scored_topic(
    title: str,
    terms: list[str],
    source_name: str = "test",
    score: float = 50.0,
    engagement: int = 100,
) -> ScoredTopic:
    """Create a ScoredTopic for testing."""
    topic_id = uuid.uuid4()
    return ScoredTopic(
        source_id=topic_id,
        source_url=f"https://example.com/{title[:10]}",
        title_original=title,
        title_normalized=title.lower(),
        title_translated=None,
        summary="Test summary",
        terms=terms,
        entities={},
        language="ko",
        content_hash=f"hash-{title[:10]}",
        metrics={"score": engagement, "comments": engagement // 10},
        metadata={"source_name": source_name, "topic_id": str(topic_id)},
        published_at=datetime.now(UTC),
        score_source=0.5,
        score_freshness=0.5,
        score_trend=0.5,
        score_relevance=0.5,
        score_total=score,
    )


class TestTopicClusterer:
    """Tests for TopicClusterer class."""

    def test_cluster_empty_list(self) -> None:
        """Empty list returns empty clusters."""
        clusterer = TopicClusterer()
        result = clusterer.cluster([])
        assert result == []

    def test_cluster_single_topic(self) -> None:
        """Single topic creates single cluster."""
        topic = make_scored_topic("Test Topic", ["ai", "tech"])
        clusterer = TopicClusterer()
        clusters = clusterer.cluster([topic])

        assert len(clusters) == 1
        assert clusters[0].primary_topic == topic
        assert clusters[0].topic_count == 1

    def test_cluster_similar_topics(self) -> None:
        """Similar topics are clustered together."""
        topic1 = make_scored_topic(
            "Claude AI 발표",
            ["claude", "ai", "anthropic"],
            source_name="reddit",
            score=80.0,
        )
        topic2 = make_scored_topic(
            "Anthropic Claude 새 버전",
            ["claude", "ai", "anthropic", "version"],
            source_name="hackernews",
            score=70.0,
        )

        clusterer = TopicClusterer(similarity_threshold=0.3)
        clusters = clusterer.cluster([topic1, topic2], total_sources=2)

        # Should be clustered together due to term overlap
        assert len(clusters) == 1
        assert clusters[0].topic_count == 2
        assert clusters[0].source_count == 2

    def test_cluster_dissimilar_topics(self) -> None:
        """Dissimilar topics create separate clusters."""
        topic1 = make_scored_topic("AI 기술 발전", ["ai", "tech", "ml"])
        topic2 = make_scored_topic("축구 월드컵 결과", ["soccer", "worldcup", "sports"])

        clusterer = TopicClusterer(similarity_threshold=0.3)
        clusters = clusterer.cluster([topic1, topic2])

        assert len(clusters) == 2


class TestSelectBestCluster:
    """Tests for select_best_cluster function."""

    def test_select_from_empty(self) -> None:
        """Empty list returns None."""
        result = select_best_cluster([])
        assert result is None

    def test_select_single_cluster(self) -> None:
        """Single cluster is selected."""
        topic = make_scored_topic("Test", ["ai"], score=50.0)
        cluster = TopicCluster(
            primary_topic=topic,
            sources={"reddit"},
            total_engagement=100,
        )

        result = select_best_cluster([cluster])
        assert result == cluster

    def test_prefer_multi_source(self) -> None:
        """Multi-source clusters are preferred over single-source."""
        # Single source, high score
        topic1 = make_scored_topic("High Score", ["ai"], score=100.0)
        single_source = TopicCluster(
            primary_topic=topic1,
            sources={"reddit"},
            total_engagement=500,
        )

        # Multi source, lower score
        topic2 = make_scored_topic("Multi Source", ["ai"], score=50.0)
        multi_source = TopicCluster(
            primary_topic=topic2,
            sources={"reddit", "hackernews", "dcinside"},
            total_engagement=300,
        )

        result = select_best_cluster(
            [single_source, multi_source],
            prefer_multi_source=True,
        )

        # Multi-source should win despite lower score
        assert result == multi_source

    def test_disable_multi_source_preference(self) -> None:
        """When disabled, highest engagement wins."""
        topic1 = make_scored_topic("High Engagement", ["ai"], score=50.0)
        high_engagement = TopicCluster(
            primary_topic=topic1,
            sources={"reddit"},
            total_engagement=1000,
        )

        topic2 = make_scored_topic("Multi Source", ["ai"], score=50.0)
        multi_source = TopicCluster(
            primary_topic=topic2,
            sources={"reddit", "hackernews"},
            total_engagement=200,
        )

        result = select_best_cluster(
            [high_engagement, multi_source],
            prefer_multi_source=False,
        )

        assert result == high_engagement

    def test_min_sources_filter(self) -> None:
        """Clusters below min_sources are filtered."""
        topic1 = make_scored_topic("Single", ["ai"], score=100.0)
        single = TopicCluster(
            primary_topic=topic1,
            sources={"reddit"},
            total_engagement=500,
        )

        topic2 = make_scored_topic("Double", ["ai"], score=50.0)
        double = TopicCluster(
            primary_topic=topic2,
            sources={"reddit", "hackernews"},
            total_engagement=200,
        )

        result = select_best_cluster(
            [single, double],
            min_sources=2,
        )

        assert result == double

    def test_fallback_when_no_match(self) -> None:
        """Returns top cluster when no match criteria."""
        topic = make_scored_topic("Only One", ["ai"], score=50.0)
        cluster = TopicCluster(
            primary_topic=topic,
            sources={"reddit"},
            total_engagement=100,
        )

        # Require 3 sources, but only 1 available
        result = select_best_cluster([cluster], min_sources=3)

        # Should fallback to top cluster
        assert result == cluster


class TestGetTopClusters:
    """Tests for get_top_clusters function."""

    def test_limit_results(self) -> None:
        """Results are limited to specified count."""
        clusters = []
        for i in range(10):
            topic = make_scored_topic(f"Topic {i}", ["ai"], score=float(i))
            clusters.append(TopicCluster(primary_topic=topic, sources={f"source{i}"}))

        result = get_top_clusters(clusters, limit=3)
        assert len(result) == 3

    def test_multi_source_first(self) -> None:
        """Multi-source clusters appear first."""
        topic1 = make_scored_topic("Single", ["ai"], score=100.0)
        single = TopicCluster(primary_topic=topic1, sources={"reddit"})

        topic2 = make_scored_topic("Multi", ["ai"], score=50.0)
        multi = TopicCluster(
            primary_topic=topic2,
            sources={"reddit", "hackernews"},
        )

        result = get_top_clusters([single, multi])

        assert result[0] == multi


class TestClusterTopics:
    """Tests for cluster_topics convenience function."""

    def test_convenience_function(self) -> None:
        """cluster_topics works as expected."""
        topics = [
            make_scored_topic("AI News", ["ai", "news"]),
            make_scored_topic("AI Update", ["ai", "update"]),
        ]

        clusters = cluster_topics(topics, similarity_threshold=0.3)

        assert len(clusters) >= 1
        assert all(isinstance(c, TopicCluster) for c in clusters)
