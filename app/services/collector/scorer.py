"""Topic scoring service.

Calculates comprehensive scores for topics based on multiple factors:
- Source credibility
- Freshness (time decay)
- Trend momentum
- Channel relevance (term and entity matching)
- Novelty (not covered before)
- Series bonus (continuation of successful series)
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.config import ScoringConfig, ScoringWeights
from app.core.config_loader import load_defaults
from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic, ScoredTopic

logger = get_logger(__name__)


def _get_scoring_defaults() -> dict[str, Any]:
    """Get scoring defaults from config/defaults.yaml."""
    defaults = load_defaults()
    scoring = defaults.get("scoring", {})
    return scoring if isinstance(scoring, dict) else {}


class ScoreComponents(BaseModel):
    """Individual score components before weighted aggregation."""

    source_credibility: float = Field(ge=0.0, le=1.0, description="Source trust score")
    source_score: float = Field(ge=0.0, le=1.0, description="Normalized engagement score")
    freshness: float = Field(ge=0.0, le=1.0, description="Time decay factor")
    trend_momentum: float = Field(ge=0.0, le=1.0, description="Trend rising factor")
    multi_source_bonus: float = Field(ge=0.0, le=0.3, description="Multiple sources bonus")
    term_relevance: float = Field(ge=0.0, le=1.0, description="Term match score")
    entity_relevance: float = Field(ge=0.0, le=1.0, description="Entity match score")
    novelty: float = Field(ge=0.0, le=1.0, description="Topic newness score")
    series_bonus: float = Field(ge=0.0, le=0.3, description="Series continuation bonus")


class TopicScorer:
    """Calculates comprehensive scores for topics.

    Scoring formula:
        total = sum(component * weight) + bonuses
        bonuses = multi_source_bonus + series_bonus

    Score components:
    - source_credibility: Trust level of the source (1-10 normalized to 0-1)
    - source_score: Engagement metrics from source (likes, comments, etc.)
    - freshness: Time decay based on publish time
    - trend_momentum: How fast the topic is trending
    - term_relevance: Match with channel's target terms
    - entity_relevance: Match with channel's target entities
    - novelty: Has this topic been covered before?
    - series_bonus: Part of a successful series?
    """

    def __init__(self, config: ScoringConfig | None = None):
        """Initialize scorer.

        Args:
            config: Scoring configuration (uses defaults if not provided)
        """
        self.config = config or ScoringConfig()

    def score(
        self,
        topic: NormalizedTopic,
        source_credibility: float = 5.0,
        trend_data: dict[str, Any] | None = None,
        history_terms: set[str] | None = None,
        series_performance: float | None = None,
        multi_source_count: int = 1,
    ) -> ScoredTopic:
        """Calculate comprehensive score for a topic.

        Args:
            topic: Normalized topic to score
            source_credibility: Source credibility (1-10 scale)
            trend_data: Optional trend information for terms
            history_terms: Terms from recently used topics (for novelty)
            series_performance: Performance of matching series (0-1), None if no series
            multi_source_count: Number of sources mentioning this topic

        Returns:
            ScoredTopic with all scores calculated
        """
        components = self._calculate_components(
            topic=topic,
            source_credibility=source_credibility,
            trend_data=trend_data or {},
            history_terms=history_terms or set(),
            series_performance=series_performance,
            multi_source_count=multi_source_count,
        )

        # Calculate weighted sum
        weights = self.config.weights
        weighted_score = (
            components.source_credibility * weights.source_credibility
            + components.source_score * weights.source_score
            + components.freshness * weights.freshness
            + components.trend_momentum * weights.trend_momentum
            + components.term_relevance * weights.term_relevance
            + components.entity_relevance * weights.entity_relevance
            + components.novelty * weights.novelty
        )

        # Add bonuses (not weighted)
        total_score = weighted_score + components.multi_source_bonus + components.series_bonus

        # Convert to 0-100 scale
        total_score_100 = int(min(100, max(0, total_score * 100)))

        # Calculate relevance as average of term, entity relevance
        relevance = (components.term_relevance + components.entity_relevance) / 2

        logger.debug(
            "Topic scored",
            title=topic.title_normalized[:50],
            total=total_score_100,
            freshness=round(components.freshness, 2),
            relevance=round(relevance, 2),
            trend=round(components.trend_momentum, 2),
        )

        return ScoredTopic(
            **topic.model_dump(),
            score_source=components.source_score,
            score_freshness=components.freshness,
            score_trend=components.trend_momentum,
            score_relevance=relevance,
            score_total=total_score_100,
        )

    def _calculate_components(
        self,
        topic: NormalizedTopic,
        source_credibility: float,
        trend_data: dict[str, Any],
        history_terms: set[str],
        series_performance: float | None,
        multi_source_count: int,
    ) -> ScoreComponents:
        """Calculate individual score components.

        Args:
            topic: Topic to score
            source_credibility: Source credibility (1-10)
            trend_data: Trend momentum data
            history_terms: Previously used terms
            series_performance: Series performance (0-1) or None
            multi_source_count: Number of sources

        Returns:
            ScoreComponents with all values calculated
        """
        return ScoreComponents(
            source_credibility=self._calc_source_credibility(source_credibility),
            source_score=self._calc_source_score(topic),
            freshness=self._calc_freshness(topic.published_at),
            trend_momentum=self._calc_trend_momentum(topic.terms, trend_data),
            multi_source_bonus=self._calc_multi_source_bonus(multi_source_count),
            term_relevance=self._calc_term_relevance(topic.terms),
            entity_relevance=self._calc_entity_relevance(topic.entities),
            novelty=self._calc_novelty(topic.terms, history_terms),
            series_bonus=self._calc_series_bonus(series_performance),
        )

    def _calc_source_credibility(self, credibility: float) -> float:
        """Normalize source credibility to 0-1 scale.

        Args:
            credibility: Source credibility (1-10 scale)

        Returns:
            Normalized credibility (0-1)
        """
        defaults = _get_scoring_defaults()
        credibility_scale = float(defaults.get("source_credibility_scale", 10.0))
        return max(0.0, min(1.0, credibility / credibility_scale))

    def _calc_source_score(self, topic: NormalizedTopic) -> float:
        """Calculate normalized source engagement score.

        Uses metrics from the source (upvotes, comments, etc.)
        Already normalized during collection, so just pass through.

        Args:
            topic: Topic with metrics

        Returns:
            Normalized source score (0-1)
        """
        # metrics.score is already normalized during normalization phase
        # If not available, return neutral score
        if topic.metrics and "normalized_score" in topic.metrics:
            return float(topic.metrics["normalized_score"])
        defaults = _get_scoring_defaults()
        return float(defaults.get("default_source_score", 0.5))

    def _calc_freshness(self, published_at: datetime | None) -> float:
        """Calculate freshness score with exponential decay.

        Uses half-life decay: score = max(min_freshness, 2^(-hours/half_life))

        Args:
            published_at: Publication timestamp

        Returns:
            Freshness score (0-1)
        """
        if published_at is None:
            return self.config.freshness_min

        now = datetime.now(UTC)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)

        age_hours = (now - published_at).total_seconds() / 3600.0

        if age_hours <= 0:
            return 1.0

        # Exponential decay with half-life
        half_life = self.config.freshness_half_life_hours
        defaults = _get_scoring_defaults()
        decay_base = defaults.get("freshness_decay_base", 2.0)
        freshness = decay_base ** (-age_hours / half_life)

        return float(max(self.config.freshness_min, freshness))

    def _calc_trend_momentum(self, terms: list[str], trend_data: dict[str, Any]) -> float:
        """Calculate trend momentum based on term trends.

        Args:
            terms: Topic terms
            trend_data: Dict mapping terms to momentum scores (0-1)

        Returns:
            Average trend momentum (0-1)
        """
        if not terms or not trend_data:
            return 0.0

        momentums = []
        for term in terms:
            term_lower = term.lower()
            if term_lower in trend_data:
                momentum = trend_data[term_lower]
                if isinstance(momentum, (int, float)):
                    momentums.append(float(momentum))

        if not momentums:
            return 0.0

        return sum(momentums) / len(momentums)

    def _calc_multi_source_bonus(self, source_count: int) -> float:
        """Calculate bonus for topics mentioned by multiple sources.

        More sources = more likely to be important news.

        Args:
            source_count: Number of sources mentioning this topic

        Returns:
            Bonus score (0-0.3)
        """
        if source_count <= 1:
            return 0.0

        defaults = _get_scoring_defaults()
        bonuses = defaults.get("multi_source_bonuses", {2: 0.1, 3: 0.2, 4: 0.3})

        if source_count == 2:
            return float(bonuses.get(2, 0.1))
        if source_count == 3:
            return float(bonuses.get(3, 0.2))
        return float(bonuses.get(4, 0.3))  # Cap at bonus for 4+ sources

    def _calc_term_relevance(self, terms: list[str]) -> float:
        """Calculate term match with channel targets.

        Args:
            terms: Topic terms

        Returns:
            Term relevance (0-1)
        """
        target_terms = self.config.target_terms
        if not target_terms or not terms:
            return 0.5  # Neutral if no targets defined

        topic_set = {t.lower() for t in terms}
        target_set = {t.lower() for t in target_terms}

        intersection = len(topic_set & target_set)
        union = len(topic_set | target_set)

        if union == 0:
            return 0.5

        return intersection / union

    def _calc_entity_relevance(self, entities: dict[str, list[str]]) -> float:
        """Calculate entity match with channel targets.

        Args:
            entities: Topic entities {type: [names]}

        Returns:
            Entity relevance (0-1)
        """
        target_entities = self.config.target_entities
        if not target_entities:
            return 0.5  # Neutral if no targets defined

        # Flatten entity names
        all_entities: set[str] = set()
        for entity_list in entities.values():
            all_entities.update(e.lower() for e in entity_list)

        if not all_entities:
            return 0.5

        target_set = {e.lower() for e in target_entities}

        intersection = len(all_entities & target_set)
        union = len(all_entities | target_set)

        if union == 0:
            return 0.5

        return intersection / union

    def _calc_novelty(self, terms: list[str], history_terms: set[str]) -> float:
        """Calculate novelty score based on term overlap with history.

        Lower overlap = higher novelty (topic not covered recently).

        Args:
            terms: Topic terms
            history_terms: Terms from recently used topics

        Returns:
            Novelty score (0-1)
        """
        if not terms:
            return 0.5

        if not history_terms:
            return 1.0  # Completely novel if no history

        topic_set = {t.lower() for t in terms}
        history_set = {t.lower() for t in history_terms}

        overlap = len(topic_set & history_set)
        total = len(topic_set)

        if total == 0:
            return 0.5

        # Novelty = 1 - overlap_ratio
        overlap_ratio = overlap / total
        return 1.0 - overlap_ratio

    def _calc_series_bonus(self, series_performance: float | None) -> float:
        """Calculate bonus for topics that match a successful series.

        Args:
            series_performance: Average performance of series (0-1), None if no match

        Returns:
            Series bonus (0-0.3)
        """
        if series_performance is None:
            return 0.0

        defaults = _get_scoring_defaults()
        series_config = defaults.get("series_performance", {})
        high_threshold = float(series_config.get("high_threshold", 0.8))
        medium_threshold = float(series_config.get("medium_threshold", 0.5))
        high_bonus = float(series_config.get("high_bonus", 0.3))
        medium_bonus = float(series_config.get("medium_bonus", 0.15))
        low_bonus = float(series_config.get("low_bonus", 0.05))

        if series_performance >= high_threshold:
            return high_bonus
        if series_performance >= medium_threshold:
            return medium_bonus
        return low_bonus


# Re-export config classes for backward compatibility
__all__ = ["TopicScorer", "ScoringConfig", "ScoringWeights", "ScoreComponents"]
