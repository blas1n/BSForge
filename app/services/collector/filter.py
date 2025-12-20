"""Topic filtering service.

Filtering happens after normalization, before scoring.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.config.filtering import FilteringConfig
from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class FilterReason(str, Enum):
    """Reason for filter decision."""

    EXCLUDED_TERM = "excluded_term"
    NO_INCLUDE_MATCH = "no_include_match"


class FilterResult(BaseModel):
    """Result of topic filtering.

    Attributes:
        passed: Whether the topic passed filtering
        reason: Reason for rejection (if not passed)
        matched_terms: Terms that matched include filters
    """

    passed: bool
    reason: FilterReason | None = None
    matched_terms: list[str] = Field(default_factory=list)


class TopicFilter:
    """Filters topics based on include/exclude rules.

    Attributes:
        config: Filtering configuration
    """

    def __init__(self, config: FilteringConfig | None = None):
        """Initialize topic filter.

        Args:
            config: Filter configuration (uses empty config if not provided)
        """
        self.config = config or FilteringConfig()
        self._include = {t.lower() for t in self.config.include}
        self._exclude = {t.lower() for t in self.config.exclude}

    def filter(self, topic: NormalizedTopic) -> FilterResult:
        """Filter a topic based on configured rules.

        Args:
            topic: Normalized topic to filter

        Returns:
            FilterResult with pass/fail status and details
        """
        searchable_text = self._build_searchable_text(topic)

        # Step 1: Check exclude terms (hard reject)
        for term in self._exclude:
            if term in searchable_text:
                logger.debug(
                    "Topic excluded by term",
                    title=topic.title_normalized[:50],
                    excluded_term=term,
                )
                return FilterResult(
                    passed=False,
                    reason=FilterReason.EXCLUDED_TERM,
                )

        # Step 2: Check include terms (at least one must match)
        matched_terms = []
        if self._include:
            for term in self._include:
                if term in searchable_text:
                    matched_terms.append(term)

            if not matched_terms:
                logger.debug(
                    "Topic rejected: no include term match",
                    title=topic.title_normalized[:50],
                )
                return FilterResult(
                    passed=False,
                    reason=FilterReason.NO_INCLUDE_MATCH,
                )

            logger.debug(
                "Topic matched terms",
                title=topic.title_normalized[:50],
                matched_terms=matched_terms[:5],
            )

        return FilterResult(
            passed=True,
            matched_terms=matched_terms,
        )

    def _build_searchable_text(self, topic: NormalizedTopic) -> str:
        """Build searchable text from topic fields.

        Args:
            topic: Normalized topic

        Returns:
            Lowercase searchable text
        """
        parts = [
            topic.title_normalized.lower(),
            " ".join(t.lower() for t in topic.terms),
        ]
        return " ".join(parts)


__all__ = [
    "TopicFilter",
    "FilterResult",
    "FilterReason",
]
