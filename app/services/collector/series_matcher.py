"""Series matching service.

This module implements topic-to-series matching based on term overlap.

Series detection (based on performance data) is implemented
separately in the analyzer phase.
"""

from pydantic import BaseModel, Field

from app.config.series import SeriesConfig, SeriesMatcherConfig
from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class SeriesMatchResult(BaseModel):
    """Result of series matching.

    Attributes:
        matched: Whether the topic matched any series
        series_id: ID of matched series (if matched)
        series_name: Name of matched series (if matched)
        similarity: Similarity score (0-1)
        matched_terms: Terms that matched
    """

    matched: bool
    series_id: str | None = None
    series_name: str | None = None
    similarity: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)


class SeriesMatcher:
    """Matches topics to existing series.

    Uses term overlap to determine if a topic belongs to a configured series.

    Attributes:
        config: Series matcher configuration
    """

    def __init__(self, config: SeriesMatcherConfig | None = None):
        """Initialize series matcher.

        Args:
            config: Matcher configuration (uses empty config if not provided)
        """
        self.config = config or SeriesMatcherConfig()
        self._build_lookup_tables()

    def _build_lookup_tables(self) -> None:
        """Build lookup tables for efficient matching.

        Config values are already lowercased by Pydantic validators,
        so no conversion needed here.
        """
        self._series_lookup: dict[str, tuple[SeriesConfig, set[str]]] = {}

        for series in self.config.series:
            if not series.enabled:
                continue

            # Already lowercase from config validators
            terms = set(series.criteria.terms)

            self._series_lookup[series.id] = (series, terms)

    def match(self, topic: NormalizedTopic) -> SeriesMatchResult:
        """Match a topic against configured series.

        Args:
            topic: Normalized topic to match (terms already lowercase)

        Returns:
            SeriesMatchResult with match details
        """
        if not self.config.enabled or not self._series_lookup:
            return SeriesMatchResult(matched=False)

        topic_terms = set(topic.terms)

        best_match: SeriesMatchResult | None = None
        best_similarity = 0.0

        for series_id, (series, terms) in self._series_lookup.items():
            # Calculate term overlap
            term_matches = topic_terms & terms
            similarity = len(term_matches) / len(terms) if terms else 0.0

            # Check if meets minimum threshold
            if similarity >= series.criteria.min_similarity and similarity > best_similarity:
                best_similarity = similarity
                best_match = SeriesMatchResult(
                    matched=True,
                    series_id=series_id,
                    series_name=series.name,
                    similarity=similarity,
                    matched_terms=list(term_matches),
                )

        if best_match:
            logger.debug(
                "Topic matched to series",
                title=topic.title_normalized[:50],
                series_name=best_match.series_name,
                similarity=best_match.similarity,
            )
            return best_match

        return SeriesMatchResult(matched=False)

    def get_score_boost(self, match_result: SeriesMatchResult) -> float:
        """Get score boost for matched series.

        Args:
            match_result: Result from match()

        Returns:
            Score boost (0-1) based on match similarity
        """
        if not match_result.matched:
            return 0.0

        # Scale boost by similarity
        # Full boost at similarity=1.0, proportionally less at lower similarities
        return self.config.boost_matched_topics * match_result.similarity


__all__ = [
    "SeriesMatcher",
    "SeriesMatchResult",
]
