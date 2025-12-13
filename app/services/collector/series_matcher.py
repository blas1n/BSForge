"""Series matching service.

This module implements topic-to-series matching based on
keywords and categories overlap.

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
        matched_keywords: Keywords that matched
        matched_categories: Categories that matched
    """

    matched: bool
    series_id: str | None = None
    series_name: str | None = None
    similarity: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    matched_categories: list[str] = Field(default_factory=list)


class SeriesMatcher:
    """Matches topics to existing series.

    Uses keyword and category overlap to determine if a topic
    belongs to a configured series.

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
        self._series_lookup: dict[str, tuple[SeriesConfig, set[str], set[str]]] = {}

        for series in self.config.series:
            if not series.enabled:
                continue

            # Already lowercase from config validators
            keywords = set(series.criteria.keywords)
            categories = set(series.criteria.categories)

            self._series_lookup[series.id] = (series, keywords, categories)

    def match(self, topic: NormalizedTopic) -> SeriesMatchResult:
        """Match a topic against configured series.

        Args:
            topic: Normalized topic to match (keywords/categories already lowercase)

        Returns:
            SeriesMatchResult with match details
        """
        if not self.config.enabled or not self._series_lookup:
            return SeriesMatchResult(matched=False)

        topic_keywords = set(topic.keywords)
        topic_categories = set(topic.categories)

        best_match: SeriesMatchResult | None = None
        best_similarity = 0.0

        for series_id, (series, keywords, categories) in self._series_lookup.items():
            # Calculate keyword overlap
            keyword_matches = topic_keywords & keywords
            keyword_similarity = len(keyword_matches) / len(keywords) if keywords else 0.0

            # Calculate category overlap
            category_matches = topic_categories & categories
            category_similarity = len(category_matches) / len(categories) if categories else 0.0

            # Combined similarity (average of keyword and category)
            # If one is empty, use only the other
            if keywords and categories:
                similarity = (keyword_similarity + category_similarity) / 2
            elif keywords:
                similarity = keyword_similarity
            elif categories:
                similarity = category_similarity
            else:
                similarity = 0.0

            # Check if meets minimum threshold
            if similarity >= series.criteria.min_similarity and similarity > best_similarity:
                best_similarity = similarity
                best_match = SeriesMatchResult(
                    matched=True,
                    series_id=series_id,
                    series_name=series.name,
                    similarity=similarity,
                    matched_keywords=list(keyword_matches),
                    matched_categories=list(category_matches),
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
