"""Topic filtering service.

This module implements category and keyword-based filtering
to include relevant topics and exclude unwanted ones.

Filtering happens after normalization, before scoring.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.config.filtering import TopicFilterConfig
from app.core.logging import get_logger
from app.services.collector.base import NormalizedTopic

logger = get_logger(__name__)


class FilterReason(str, Enum):
    """Reason for filter decision."""

    EXCLUDED_CATEGORY = "excluded_category"
    EXCLUDED_KEYWORD = "excluded_keyword"
    NO_CATEGORY_MATCH = "no_category_match"
    NO_KEYWORD_MATCH = "no_keyword_match"


class FilterResult(BaseModel):
    """Result of topic filtering.

    Attributes:
        passed: Whether the topic passed filtering
        reason: Reason for rejection (if not passed)
        matched_categories: Categories that matched include filters
        matched_keywords: Keywords that matched include filters
        category_weight: Combined weight from matched categories
        keyword_weight: Combined weight from matched keywords
    """

    passed: bool
    reason: FilterReason | None = None
    matched_categories: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    category_weight: float = 1.0
    keyword_weight: float = 1.0


class TopicFilter:
    """Filters topics based on category and keyword rules.

    Applies include/exclude filters to determine if a topic
    should be processed further in the pipeline.

    Attributes:
        config: Topic filter configuration
    """

    def __init__(self, config: TopicFilterConfig | None = None):
        """Initialize topic filter.

        Args:
            config: Filter configuration (uses empty config if not provided)
        """
        self.config = config or TopicFilterConfig()
        self._build_lookup_tables()

    def _build_lookup_tables(self) -> None:
        """Build lookup tables for efficient filtering.

        Config values are already lowercased by Pydantic validators,
        so no conversion needed here.
        """
        # Exclude lookups (already lowercase from config)
        self._excluded_categories = set(self.config.exclude.categories)
        self._excluded_keywords = set(self.config.exclude.keywords)

        # Include category lookup: name -> (weight, subcategories)
        self._include_categories: dict[str, tuple[float, set[str]]] = {}
        for cat in self.config.include.categories:
            subcats = set(cat.subcategories)
            self._include_categories[cat.name] = (cat.weight, subcats)

        # Include keyword lookup: keyword -> weight (including synonyms)
        self._include_keywords: dict[str, float] = {}
        for kw in self.config.include.keywords:
            self._include_keywords[kw.keyword] = kw.weight
            for syn in kw.synonyms:
                self._include_keywords[syn] = kw.weight

    def filter(self, topic: NormalizedTopic) -> FilterResult:
        """Filter a topic based on configured rules.

        Args:
            topic: Normalized topic to filter

        Returns:
            FilterResult with pass/fail status and details
        """
        # Step 1: Check exclude filters (hard reject)
        exclude_result = self._check_excludes(topic)
        if exclude_result is not None:
            return exclude_result

        # Step 2: Check include filters
        matched_cats, cat_weight = self._match_categories(topic)
        matched_kws, kw_weight = self._match_keywords(topic)

        # Step 3: Check required matches
        if self.config.require_category_match and not matched_cats:
            logger.debug(
                "Topic rejected: no category match",
                title=topic.title_normalized[:50],
                categories=topic.categories,
            )
            return FilterResult(
                passed=False,
                reason=FilterReason.NO_CATEGORY_MATCH,
            )

        if self.config.require_keyword_match and not matched_kws:
            logger.debug(
                "Topic rejected: no keyword match",
                title=topic.title_normalized[:50],
                keywords=topic.keywords[:5],
            )
            return FilterResult(
                passed=False,
                reason=FilterReason.NO_KEYWORD_MATCH,
            )

        # Topic passed
        if matched_cats or matched_kws:
            logger.debug(
                "Topic passed with matches",
                title=topic.title_normalized[:50],
                matched_categories=matched_cats,
                matched_keywords=matched_kws[:5],
            )

        return FilterResult(
            passed=True,
            matched_categories=matched_cats,
            matched_keywords=matched_kws,
            category_weight=cat_weight,
            keyword_weight=kw_weight,
        )

    def _check_excludes(self, topic: NormalizedTopic) -> FilterResult | None:
        """Check if topic matches any exclude filters.

        Args:
            topic: Topic to check (categories/keywords already lowercase)

        Returns:
            FilterResult if excluded, None if not excluded
        """
        # Check excluded categories (topic.categories already lowercase)
        topic_categories = set(topic.categories)
        excluded_cat = topic_categories & self._excluded_categories
        if excluded_cat:
            logger.info(
                "Topic excluded by category",
                title=topic.title_normalized[:50],
                excluded_categories=list(excluded_cat),
            )
            return FilterResult(
                passed=False,
                reason=FilterReason.EXCLUDED_CATEGORY,
            )

        # Check excluded keywords in title and keywords (already lowercase)
        text_to_check = f"{topic.title_normalized} {' '.join(topic.keywords)}"
        for excluded_kw in self._excluded_keywords:
            if excluded_kw in text_to_check:
                logger.info(
                    "Topic excluded by keyword",
                    title=topic.title_normalized[:50],
                    excluded_keyword=excluded_kw,
                )
                return FilterResult(
                    passed=False,
                    reason=FilterReason.EXCLUDED_KEYWORD,
                )

        return None

    def _match_categories(self, topic: NormalizedTopic) -> tuple[list[str], float]:
        """Match topic categories against include filters.

        Args:
            topic: Topic to check (categories already lowercase)

        Returns:
            Tuple of (matched category names, combined weight)
        """
        if not self._include_categories:
            return [], 1.0

        matched = []
        total_weight = 0.0
        topic_categories = set(topic.categories)  # Already lowercase

        for cat_name, (weight, subcats) in self._include_categories.items():
            # Direct match
            if cat_name in topic_categories or subcats & topic_categories:
                matched.append(cat_name)
                total_weight += weight

        # Normalize weight (average if multiple matches, minimum 1.0)
        avg_weight = total_weight / len(matched) if matched else 1.0
        return matched, max(avg_weight, 1.0)

    def _match_keywords(self, topic: NormalizedTopic) -> tuple[list[str], float]:
        """Match topic keywords against include filters.

        Args:
            topic: Topic to check (title_normalized and keywords already lowercase)

        Returns:
            Tuple of (matched keywords, combined weight)
        """
        if not self._include_keywords:
            return [], 1.0

        matched = []
        total_weight = 0.0
        text_to_check = f"{topic.title_normalized} {' '.join(topic.keywords)}"  # Already lowercase

        for keyword, weight in self._include_keywords.items():
            if keyword in text_to_check:
                matched.append(keyword)
                total_weight += weight

        # Normalize weight
        avg_weight = total_weight / len(matched) if matched else 1.0
        return matched, max(avg_weight, 1.0)


__all__ = [
    "TopicFilter",
    "FilterResult",
    "FilterReason",
]
