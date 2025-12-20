"""Unit tests for TopicScorer.

Tests cover:
- Individual score component calculations
- Weighted score aggregation
- Freshness decay
- Trend momentum
- Term/entity relevance
- Novelty scoring
- Series and multi-source bonuses
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import HttpUrl

from app.services.collector.base import NormalizedTopic, ScoredTopic
from app.services.collector.scorer import (
    ScoringConfig,
    ScoringWeights,
    TopicScorer,
)


def create_normalized_topic(
    title: str = "Test Topic",
    terms: list[str] | None = None,
    entities: dict[str, list[str]] | None = None,
    published_at: datetime | None = None,
    metrics: dict | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic."""
    return NormalizedTopic(
        source_id=uuid.uuid4(),
        source_url=HttpUrl("https://example.com/topic"),
        title_original=title,
        title_normalized=title.lower(),
        summary=f"Summary of {title}",
        terms=terms or ["tech", "test", "topic"],
        entities=entities or {},
        language="en",
        published_at=published_at or datetime.now(UTC),
        content_hash=f"hash_{uuid.uuid4().hex[:8]}",
        metrics=metrics or {"normalized_score": 0.5},
    )


@pytest.fixture
def scorer() -> TopicScorer:
    """Create a TopicScorer with default config."""
    return TopicScorer()


@pytest.fixture
def scorer_with_targets() -> TopicScorer:
    """Create a TopicScorer with target terms."""
    config = ScoringConfig(
        target_terms=["tech", "ai", "programming", "python", "machine learning", "api"],
        target_entities=["OpenAI", "Google", "Microsoft"],
    )
    return TopicScorer(config=config)


class TestSourceCredibility:
    """Tests for source credibility scoring."""

    def test_source_credibility_normalization(self, scorer: TopicScorer):
        """Test credibility is normalized to 0-1 scale."""
        # 10/10 credibility
        assert scorer._calc_source_credibility(10.0) == 1.0

        # 5/10 credibility
        assert scorer._calc_source_credibility(5.0) == 0.5

        # 1/10 credibility
        assert scorer._calc_source_credibility(1.0) == 0.1

    def test_source_credibility_bounds(self, scorer: TopicScorer):
        """Test credibility stays within bounds."""
        # Above 10
        assert scorer._calc_source_credibility(15.0) == 1.0

        # Below 0
        assert scorer._calc_source_credibility(-5.0) == 0.0


class TestSourceScore:
    """Tests for source engagement score."""

    def test_source_score_from_metrics(self, scorer: TopicScorer):
        """Test source score extraction from metrics."""
        topic = create_normalized_topic(metrics={"normalized_score": 0.8})
        assert scorer._calc_source_score(topic) == 0.8

    def test_source_score_missing_metrics(self, scorer: TopicScorer):
        """Test default score when metrics missing."""
        topic = create_normalized_topic(metrics={})
        assert scorer._calc_source_score(topic) == 0.5  # Neutral


class TestFreshness:
    """Tests for freshness decay calculation."""

    def test_freshness_brand_new(self, scorer: TopicScorer):
        """Test freshness for just-published topic."""
        now = datetime.now(UTC)
        # Allow small floating point tolerance
        assert abs(scorer._calc_freshness(now) - 1.0) < 0.0001

    def test_freshness_one_half_life(self, scorer: TopicScorer):
        """Test freshness after one half-life (24 hours default)."""
        published = datetime.now(UTC) - timedelta(hours=24)
        freshness = scorer._calc_freshness(published)
        assert abs(freshness - 0.5) < 0.01

    def test_freshness_two_half_lives(self, scorer: TopicScorer):
        """Test freshness after two half-lives (48 hours)."""
        published = datetime.now(UTC) - timedelta(hours=48)
        freshness = scorer._calc_freshness(published)
        assert abs(freshness - 0.25) < 0.01

    def test_freshness_minimum(self, scorer: TopicScorer):
        """Test freshness doesn't go below minimum."""
        # Very old topic
        published = datetime.now(UTC) - timedelta(days=30)
        freshness = scorer._calc_freshness(published)
        assert freshness >= scorer.config.freshness_min

    def test_freshness_none_published_at(self, scorer: TopicScorer):
        """Test freshness when published_at is None."""
        freshness = scorer._calc_freshness(None)
        assert freshness == scorer.config.freshness_min

    def test_freshness_custom_half_life(self):
        """Test freshness with custom half-life."""
        config = ScoringConfig(freshness_half_life_hours=12)
        scorer = TopicScorer(config=config)

        # 12 hours old should be ~0.5
        published = datetime.now(UTC) - timedelta(hours=12)
        freshness = scorer._calc_freshness(published)
        assert abs(freshness - 0.5) < 0.01


class TestTrendMomentum:
    """Tests for trend momentum calculation."""

    def test_trend_momentum_with_data(self, scorer: TopicScorer):
        """Test trend momentum from trend data."""
        terms = ["ai", "machine learning"]
        trend_data = {"ai": 0.8, "machine learning": 0.6}

        momentum = scorer._calc_trend_momentum(terms, trend_data)
        assert abs(momentum - 0.7) < 0.01  # Average of 0.8 and 0.6

    def test_trend_momentum_partial_match(self, scorer: TopicScorer):
        """Test trend momentum with partial term match."""
        terms = ["ai", "python", "web"]
        trend_data = {"ai": 0.9}  # Only one term matches

        momentum = scorer._calc_trend_momentum(terms, trend_data)
        assert momentum == 0.9

    def test_trend_momentum_no_match(self, scorer: TopicScorer):
        """Test trend momentum with no matching terms."""
        terms = ["python", "web"]
        trend_data = {"ai": 0.8}

        momentum = scorer._calc_trend_momentum(terms, trend_data)
        assert momentum == 0.0

    def test_trend_momentum_empty_data(self, scorer: TopicScorer):
        """Test trend momentum with empty data."""
        assert scorer._calc_trend_momentum(["ai"], {}) == 0.0
        assert scorer._calc_trend_momentum([], {"ai": 0.8}) == 0.0


class TestMultiSourceBonus:
    """Tests for multi-source bonus."""

    def test_multi_source_bonus_single(self, scorer: TopicScorer):
        """Test no bonus for single source."""
        assert scorer._calc_multi_source_bonus(1) == 0.0

    def test_multi_source_bonus_two(self, scorer: TopicScorer):
        """Test bonus for two sources."""
        assert scorer._calc_multi_source_bonus(2) == 0.1

    def test_multi_source_bonus_three(self, scorer: TopicScorer):
        """Test bonus for three sources."""
        assert scorer._calc_multi_source_bonus(3) == 0.2

    def test_multi_source_bonus_many(self, scorer: TopicScorer):
        """Test bonus caps at 0.3 for 4+ sources."""
        assert scorer._calc_multi_source_bonus(4) == 0.3
        assert scorer._calc_multi_source_bonus(10) == 0.3


class TestTermRelevance:
    """Tests for term relevance scoring."""

    def test_term_relevance_full_match(self, scorer_with_targets: TopicScorer):
        """Test full term match."""
        terms = ["tech", "ai"]
        relevance = scorer_with_targets._calc_term_relevance(terms)
        # Has matches in target_terms
        assert relevance > 0

    def test_term_relevance_no_match(self, scorer_with_targets: TopicScorer):
        """Test no term match."""
        terms = ["sports", "entertainment"]
        relevance = scorer_with_targets._calc_term_relevance(terms)
        assert relevance == 0.0

    def test_term_relevance_no_targets(self, scorer: TopicScorer):
        """Test neutral score when no targets configured."""
        terms = ["tech", "ai"]
        relevance = scorer._calc_term_relevance(terms)
        assert relevance == 0.5  # Neutral


class TestEntityRelevance:
    """Tests for entity relevance scoring."""

    def test_entity_relevance_match(self, scorer_with_targets: TopicScorer):
        """Test entity match."""
        entities = {"company": ["OpenAI", "Tesla"]}
        relevance = scorer_with_targets._calc_entity_relevance(entities)
        assert relevance > 0

    def test_entity_relevance_no_match(self, scorer_with_targets: TopicScorer):
        """Test no entity match."""
        entities = {"company": ["Apple", "Amazon"]}
        relevance = scorer_with_targets._calc_entity_relevance(entities)
        assert relevance == 0.0

    def test_entity_relevance_empty(self, scorer_with_targets: TopicScorer):
        """Test empty entities."""
        relevance = scorer_with_targets._calc_entity_relevance({})
        assert relevance == 0.5  # Neutral


class TestNovelty:
    """Tests for novelty scoring."""

    def test_novelty_completely_new(self, scorer: TopicScorer):
        """Test novelty for topic with no history overlap."""
        terms = ["new", "unique", "topic"]
        history = {"old", "different", "terms"}

        novelty = scorer._calc_novelty(terms, history)
        assert novelty == 1.0

    def test_novelty_full_overlap(self, scorer: TopicScorer):
        """Test novelty for topic with full history overlap."""
        terms = ["python", "api", "web"]
        history = {"python", "api", "web"}

        novelty = scorer._calc_novelty(terms, history)
        assert novelty == 0.0

    def test_novelty_partial_overlap(self, scorer: TopicScorer):
        """Test novelty for topic with partial overlap."""
        terms = ["python", "api", "new", "topic"]
        history = {"python", "api"}

        novelty = scorer._calc_novelty(terms, history)
        assert novelty == 0.5  # 2/4 overlap → 0.5 novelty

    def test_novelty_no_history(self, scorer: TopicScorer):
        """Test novelty when no history."""
        terms = ["python", "api"]
        novelty = scorer._calc_novelty(terms, set())
        assert novelty == 1.0


class TestSeriesBonus:
    """Tests for series continuation bonus."""

    def test_series_bonus_high_performance(self, scorer: TopicScorer):
        """Test bonus for high-performing series."""
        bonus = scorer._calc_series_bonus(0.9)
        assert bonus == 0.3

    def test_series_bonus_medium_performance(self, scorer: TopicScorer):
        """Test bonus for medium-performing series."""
        bonus = scorer._calc_series_bonus(0.6)
        assert bonus == 0.15

    def test_series_bonus_low_performance(self, scorer: TopicScorer):
        """Test bonus for low-performing series."""
        bonus = scorer._calc_series_bonus(0.3)
        assert bonus == 0.05

    def test_series_bonus_no_series(self, scorer: TopicScorer):
        """Test no bonus when not part of series."""
        bonus = scorer._calc_series_bonus(None)
        assert bonus == 0.0


class TestFullScoring:
    """Tests for full topic scoring."""

    def test_score_topic_basic(self, scorer: TopicScorer):
        """Test basic topic scoring."""
        topic = create_normalized_topic()

        scored = scorer.score(topic)

        assert isinstance(scored, ScoredTopic)
        assert 0 <= scored.score_total <= 100
        assert 0 <= scored.score_source <= 1
        assert 0 <= scored.score_freshness <= 1
        assert 0 <= scored.score_trend <= 1
        assert 0 <= scored.score_relevance <= 1

    def test_score_topic_with_context(self, scorer_with_targets: TopicScorer):
        """Test scoring with all context provided."""
        topic = create_normalized_topic(
            terms=["tech", "ai", "python", "machine learning"],
            entities={"company": ["OpenAI"]},
        )

        scored = scorer_with_targets.score(
            topic,
            source_credibility=8.0,
            trend_data={"python": 0.7, "machine learning": 0.8},
            history_terms={"old", "topic"},
            series_performance=0.85,
            multi_source_count=3,
        )

        # Should have high score due to matching targets and bonuses
        assert scored.score_total > 50

    def test_score_preserves_topic_data(self, scorer: TopicScorer):
        """Test that scoring preserves original topic data."""
        topic = create_normalized_topic(title="Original Title")

        scored = scorer.score(topic)

        assert scored.title_original == "Original Title"
        assert scored.title_normalized == "original title"
        assert scored.source_id == topic.source_id
        assert scored.content_hash == topic.content_hash

    def test_score_with_bonuses(self, scorer: TopicScorer):
        """Test that bonuses add to score."""
        topic = create_normalized_topic()

        # Score without bonuses
        scored_no_bonus = scorer.score(
            topic,
            multi_source_count=1,
            series_performance=None,
        )

        # Score with bonuses
        scored_with_bonus = scorer.score(
            topic,
            multi_source_count=4,  # +0.3
            series_performance=0.9,  # +0.3
        )

        # Bonus version should score higher
        assert scored_with_bonus.score_total > scored_no_bonus.score_total


class TestScoringConfig:
    """Tests for ScoringConfig model."""

    def test_default_weights(self):
        """Test default weight values."""
        config = ScoringConfig()
        weights = config.weights

        assert weights.source_credibility == 0.15
        assert weights.freshness == 0.20
        assert weights.novelty == 0.10

    def test_custom_weights(self):
        """Test custom weight configuration that sums to 1.0."""
        weights = ScoringWeights(
            source_credibility=0.10,
            source_score=0.10,
            freshness=0.30,
            trend_momentum=0.20,
            term_relevance=0.15,
            entity_relevance=0.05,
            novelty=0.10,
        )
        config = ScoringConfig(weights=weights)

        assert config.weights.freshness == 0.30
        assert config.weights.trend_momentum == 0.20

    def test_config_settings(self):
        """Test configuration settings."""
        config = ScoringConfig(
            freshness_half_life_hours=12,
            freshness_min=0.2,
            min_score_threshold=40,
        )

        assert config.freshness_half_life_hours == 12
        assert config.freshness_min == 0.2
        assert config.min_score_threshold == 40
