"""Unit tests for TopicFilter.

Tests cover:
- Exclude filters (categories and keywords)
- Include filters with weights
- Required match conditions
- Edge cases
"""

import uuid
from datetime import UTC, datetime

from pydantic import HttpUrl

from app.config.filtering import (
    CategoryFilter,
    ExcludeFilters,
    IncludeFilters,
    KeywordFilter,
    TopicFilterConfig,
)
from app.services.collector.base import NormalizedTopic
from app.services.collector.filter import (
    FilterReason,
    FilterResult,
    TopicFilter,
)


def create_topic(
    title: str = "Test Topic",
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic.

    Note: categories and keywords are lowercased to match
    the behavior of TopicNormalizer.
    """
    # Lowercase categories and keywords to match normalizer behavior
    cats = [c.lower() for c in (categories or ["tech"])]
    kws = [k.lower() for k in (keywords or ["test", "topic"])]

    return NormalizedTopic(
        source_id=uuid.uuid4(),
        source_url=HttpUrl("https://example.com/topic"),
        title_original=title,
        title_normalized=title.lower(),
        summary=f"Summary of {title}",
        categories=cats,
        keywords=kws,
        entities={},
        language="en",
        published_at=datetime.now(UTC),
        content_hash=f"hash_{uuid.uuid4().hex[:8]}",
        metrics={"score": 100},
    )


class TestExcludeFilters:
    """Tests for exclude filter functionality."""

    def test_exclude_by_category(self):
        """Test that topics with excluded categories are rejected."""
        config = TopicFilterConfig(exclude=ExcludeFilters(categories=["politics", "religion"]))
        filter = TopicFilter(config)

        topic = create_topic(categories=["politics", "tech"])
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_CATEGORY

    def test_exclude_by_keyword(self):
        """Test that topics with excluded keywords are rejected."""
        config = TopicFilterConfig(exclude=ExcludeFilters(keywords=["gambling", "casino"]))
        filter = TopicFilter(config)

        topic = create_topic(
            title="New Casino Game Released",
            keywords=["gaming", "casino"],
        )
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_KEYWORD

    def test_exclude_keyword_in_title(self):
        """Test that excluded keywords are checked in title."""
        config = TopicFilterConfig(exclude=ExcludeFilters(keywords=["spam"]))
        filter = TopicFilter(config)

        topic = create_topic(title="This is spam content")
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_KEYWORD

    def test_exclude_config_case_insensitive(self):
        """Test that config values are case-insensitive (lowercased internally)."""
        # Config uses mixed case, but should still match lowercase topic data
        config = TopicFilterConfig(exclude=ExcludeFilters(categories=["Politics", "RELIGION"]))
        filter = TopicFilter(config)

        # Topic categories are already lowercase (from normalizer)
        topic = create_topic(categories=["politics"])
        result = filter.filter(topic)

        assert result.passed is False

    def test_no_exclude_match_passes(self):
        """Test that topics not matching exclude filters pass."""
        config = TopicFilterConfig(
            exclude=ExcludeFilters(
                categories=["politics"],
                keywords=["gambling"],
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(
            categories=["tech", "ai"],
            keywords=["machine", "learning"],
        )
        result = filter.filter(topic)

        assert result.passed is True
        assert result.reason is None


class TestIncludeFilters:
    """Tests for include filter functionality."""

    def test_include_category_match(self):
        """Test that matching categories are recorded."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                categories=[
                    CategoryFilter(name="tech", weight=1.5),
                    CategoryFilter(name="ai", weight=2.0),
                ]
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["tech", "news"])
        result = filter.filter(topic)

        assert result.passed is True
        assert "tech" in result.matched_categories
        assert result.category_weight == 1.5

    def test_include_multiple_categories(self):
        """Test weight averaging with multiple category matches."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                categories=[
                    CategoryFilter(name="tech", weight=1.0),
                    CategoryFilter(name="ai", weight=2.0),
                ]
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["tech", "ai"])
        result = filter.filter(topic)

        assert result.passed is True
        assert len(result.matched_categories) == 2
        assert result.category_weight == 1.5  # (1.0 + 2.0) / 2

    def test_include_subcategory_match(self):
        """Test that subcategories trigger parent category match."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                categories=[
                    CategoryFilter(
                        name="ai",
                        weight=2.0,
                        subcategories=["llm", "image-gen", "robotics"],
                    )
                ]
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["llm", "tech"])
        result = filter.filter(topic)

        assert result.passed is True
        assert "ai" in result.matched_categories
        assert result.category_weight == 2.0

    def test_include_keyword_match(self):
        """Test that matching keywords are recorded."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                keywords=[
                    KeywordFilter(keyword="ChatGPT", weight=1.5),
                    KeywordFilter(keyword="OpenAI", weight=1.2),
                ]
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(
            title="ChatGPT Updates Released",
            keywords=["ai", "chatgpt"],
        )
        result = filter.filter(topic)

        assert result.passed is True
        assert "chatgpt" in result.matched_keywords
        assert result.keyword_weight == 1.5

    def test_include_keyword_synonyms(self):
        """Test that synonyms are matched."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                keywords=[
                    KeywordFilter(
                        keyword="ChatGPT",
                        weight=1.5,
                        synonyms=["챗지피티", "GPT"],
                    )
                ]
            )
        )
        filter = TopicFilter(config)

        topic = create_topic(title="GPT-4 Performance Analysis")
        result = filter.filter(topic)

        assert result.passed is True
        assert "gpt" in result.matched_keywords


class TestRequiredMatches:
    """Tests for required match conditions."""

    def test_require_category_match_fails(self):
        """Test rejection when category match is required but not found."""
        config = TopicFilterConfig(
            include=IncludeFilters(categories=[CategoryFilter(name="ai")]),
            require_category_match=True,
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["gaming", "news"])
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.NO_CATEGORY_MATCH

    def test_require_category_match_passes(self):
        """Test passing when required category is matched."""
        config = TopicFilterConfig(
            include=IncludeFilters(categories=[CategoryFilter(name="ai")]),
            require_category_match=True,
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["ai", "tech"])
        result = filter.filter(topic)

        assert result.passed is True

    def test_require_keyword_match_fails(self):
        """Test rejection when keyword match is required but not found."""
        config = TopicFilterConfig(
            include=IncludeFilters(keywords=[KeywordFilter(keyword="AI")]),
            require_keyword_match=True,
        )
        filter = TopicFilter(config)

        topic = create_topic(
            title="Gaming News Today",
            keywords=["gaming", "news"],
        )
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.NO_KEYWORD_MATCH

    def test_require_keyword_match_passes(self):
        """Test passing when required keyword is matched."""
        config = TopicFilterConfig(
            include=IncludeFilters(keywords=[KeywordFilter(keyword="AI")]),
            require_keyword_match=True,
        )
        filter = TopicFilter(config)

        topic = create_topic(
            title="AI News Today",
            keywords=["ai", "news"],
        )
        result = filter.filter(topic)

        assert result.passed is True

    def test_exclude_checked_before_require(self):
        """Test that exclude filters are checked before required matches."""
        config = TopicFilterConfig(
            include=IncludeFilters(categories=[CategoryFilter(name="tech")]),
            exclude=ExcludeFilters(keywords=["spam"]),
            require_category_match=True,
        )
        filter = TopicFilter(config)

        # Topic matches required category but has excluded keyword
        topic = create_topic(
            title="Tech Spam Alert",
            categories=["tech"],
        )
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_KEYWORD


class TestEdgeCases:
    """Tests for edge cases and default behavior."""

    def test_empty_config_passes_all(self):
        """Test that empty config passes all topics."""
        filter = TopicFilter()  # Default empty config

        topic = create_topic(categories=["anything"], keywords=["whatever"])
        result = filter.filter(topic)

        assert result.passed is True
        assert result.category_weight == 1.0
        assert result.keyword_weight == 1.0

    def test_empty_topic_categories(self):
        """Test handling of topic with no categories."""
        config = TopicFilterConfig(exclude=ExcludeFilters(categories=["politics"]))
        filter = TopicFilter(config)

        topic = create_topic(categories=[])
        result = filter.filter(topic)

        assert result.passed is True

    def test_empty_topic_keywords(self):
        """Test handling of topic with no keywords."""
        config = TopicFilterConfig(exclude=ExcludeFilters(keywords=["spam"]))
        filter = TopicFilter(config)

        topic = create_topic(title="Clean Title", keywords=[])
        result = filter.filter(topic)

        assert result.passed is True

    def test_minimum_weight_is_one(self):
        """Test that weights are never below 1.0."""
        config = TopicFilterConfig(
            include=IncludeFilters(categories=[CategoryFilter(name="tech", weight=0.5)])
        )
        filter = TopicFilter(config)

        topic = create_topic(categories=["tech"])
        result = filter.filter(topic)

        # Weight should be at least 1.0
        assert result.category_weight >= 1.0


class TestFilterResult:
    """Tests for FilterResult model."""

    def test_passed_result(self):
        """Test creating a passed result."""
        result = FilterResult(
            passed=True,
            matched_categories=["tech", "ai"],
            matched_keywords=["chatgpt"],
            category_weight=1.5,
            keyword_weight=1.2,
        )

        assert result.passed is True
        assert result.reason is None
        assert len(result.matched_categories) == 2

    def test_failed_result(self):
        """Test creating a failed result."""
        result = FilterResult(
            passed=False,
            reason=FilterReason.EXCLUDED_CATEGORY,
        )

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_CATEGORY
        assert result.matched_categories == []


class TestFilterReason:
    """Tests for FilterReason enum."""

    def test_reason_values(self):
        """Test FilterReason enum values."""
        assert FilterReason.EXCLUDED_CATEGORY.value == "excluded_category"
        assert FilterReason.EXCLUDED_KEYWORD.value == "excluded_keyword"
        assert FilterReason.NO_CATEGORY_MATCH.value == "no_category_match"
        assert FilterReason.NO_KEYWORD_MATCH.value == "no_keyword_match"
