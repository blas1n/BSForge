"""Unified term-based topic filtering.

This module provides a simple term filter that matches topics against
include and exclude terms. Terms are matched against:
- Title (normalized, lowercase)
- Keywords
- Categories

This replaces the previous separate keyword/category filtering system.
"""

from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class TermFilter:
    """Filters topics based on unified include/exclude terms.

    Terms are matched against title, keywords, and categories.
    A topic passes if:
    1. It matches at least one include term (if include_terms is specified)
    2. It does NOT match any exclude term

    Attributes:
        include_terms: Terms that must be matched (at least one)
        exclude_terms: Terms that must NOT be matched (any)
    """

    def __init__(
        self,
        include_terms: list[str] | None = None,
        exclude_terms: list[str] | None = None,
    ):
        """Initialize term filter.

        Args:
            include_terms: Terms to include (lowercase on init)
            exclude_terms: Terms to exclude (lowercase on init)
        """
        self._include_terms = {t.lower() for t in (include_terms or [])}
        self._exclude_terms = {t.lower() for t in (exclude_terms or [])}

    def matches(self, topic: NormalizedTopic) -> bool:
        """Check if a topic matches the filter criteria.

        Args:
            topic: Normalized topic to check

        Returns:
            True if topic passes filter, False otherwise
        """
        # Build searchable text from topic (all lowercase)
        searchable_text = self._build_searchable_text(topic)

        # Step 1: Check exclude terms first (hard reject)
        for term in self._exclude_terms:
            if term in searchable_text:
                logger.debug(
                    "Topic excluded by term",
                    title=topic.title_normalized[:50],
                    excluded_term=term,
                )
                return False

        # Step 2: Check include terms (at least one must match)
        if self._include_terms:
            matched = False
            matched_terms = []
            for term in self._include_terms:
                if term in searchable_text:
                    matched = True
                    matched_terms.append(term)

            if not matched:
                logger.debug(
                    "Topic rejected: no include term match",
                    title=topic.title_normalized[:50],
                )
                return False

            logger.debug(
                "Topic matched terms",
                title=topic.title_normalized[:50],
                matched_terms=matched_terms[:5],
            )

        return True

    def _build_searchable_text(self, topic: NormalizedTopic) -> str:
        """Build searchable text from topic fields.

        Combines title, keywords, and categories into a single
        lowercase string for term matching.

        Args:
            topic: Normalized topic

        Returns:
            Lowercase searchable text
        """
        parts = [
            topic.title_normalized.lower(),
            " ".join(kw.lower() for kw in topic.keywords),
            " ".join(cat.lower() for cat in topic.categories),
        ]
        return " ".join(parts)


__all__ = ["TermFilter"]
