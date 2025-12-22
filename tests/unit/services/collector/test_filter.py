"""Unit tests for TopicFilter.

Tests cover:
- Exclude filters (terms)
- Include filters
- Edge cases
"""

import uuid
from datetime import UTC, datetime

from pydantic import HttpUrl

from app.config.filtering import FilteringConfig
from app.services.collector.base import NormalizedTopic
from app.services.collector.filter import (
    FilterReason,
    FilterResult,
    TopicFilter,
)


def create_topic(
    title: str = "Test Topic",
    terms: list[str] | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic.

    Note: terms are lowercased to match the behavior of TopicNormalizer.
    """
    # Lowercase terms to match normalizer behavior
    topic_terms = [t.lower() for t in (terms or ["tech", "test", "topic"])]

    return NormalizedTopic(
        source_id=uuid.uuid4(),
        source_url=HttpUrl("https://example.com/topic"),
        title_original=title,
        title_normalized=title.lower(),
        summary=f"Summary of {title}",
        terms=topic_terms,
        entities={},
        language="en",
        published_at=datetime.now(UTC),
        content_hash=f"hash_{uuid.uuid4().hex[:8]}",
        metrics={"score": 100},
    )


class TestExcludeFilters:
    """Tests for exclude filter functionality."""

    def test_exclude_by_term(self):
        """Test that topics with excluded terms are rejected."""
        config = FilteringConfig(exclude=["politics", "religion"])
        filter = TopicFilter(config)

        topic = create_topic(terms=["politics", "tech"])
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_TERM

    def test_exclude_term_in_title(self):
        """Test that excluded terms are checked in title."""
        config = FilteringConfig(exclude=["spam"])
        filter = TopicFilter(config)

        topic = create_topic(title="This is spam content")
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_TERM

    def test_exclude_config_case_insensitive(self):
        """Test that config values are case-insensitive (lowercased internally)."""
        config = FilteringConfig(exclude=["Politics", "RELIGION"])
        filter = TopicFilter(config)

        # Topic terms are already lowercase (from normalizer)
        topic = create_topic(terms=["politics"])
        result = filter.filter(topic)

        assert result.passed is False

    def test_no_exclude_match_passes(self):
        """Test that topics not matching excludes pass."""
        config = FilteringConfig(exclude=["politics", "gambling"])
        filter = TopicFilter(config)

        topic = create_topic(terms=["tech", "ai"])
        result = filter.filter(topic)

        assert result.passed is True


class TestIncludeFilters:
    """Tests for include filter functionality."""

    def test_include_match_passes(self):
        """Test that matching include terms pass."""
        config = FilteringConfig(include=["tech", "ai"])
        filter = TopicFilter(config)

        topic = create_topic(terms=["tech", "news"])
        result = filter.filter(topic)

        assert result.passed is True
        assert "tech" in result.matched_terms

    def test_include_multiple_matches(self):
        """Test multiple include term matches."""
        config = FilteringConfig(include=["tech", "ai", "programming"])
        filter = TopicFilter(config)

        topic = create_topic(terms=["tech", "ai"])
        result = filter.filter(topic)

        assert result.passed is True
        assert len(result.matched_terms) == 2

    def test_no_include_match_fails(self):
        """Test that topics not matching includes fail."""
        config = FilteringConfig(include=["ai"])
        filter = TopicFilter(config)

        topic = create_topic(terms=["gaming", "news"])
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.NO_INCLUDE_MATCH


class TestCombinedFilters:
    """Tests for combined include/exclude filters."""

    def test_exclude_takes_priority(self):
        """Test that exclude filters take priority over include."""
        config = FilteringConfig(
            include=["tech"],
            exclude=["spam"],
        )
        filter = TopicFilter(config)

        # Topic matches include but also has excluded term
        topic = create_topic(
            title="Tech spam content",
            terms=["tech"],
        )
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.EXCLUDED_TERM

    def test_empty_filters_pass_all(self):
        """Test that empty filters pass all topics."""
        config = FilteringConfig()
        filter = TopicFilter(config)

        topic = create_topic(terms=["anything", "whatever"])
        result = filter.filter(topic)

        assert result.passed is True


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_topic_terms(self):
        """Test handling of topic with no terms."""
        config = FilteringConfig(exclude=["politics"])
        filter = TopicFilter(config)

        topic = create_topic(terms=[])
        result = filter.filter(topic)

        assert result.passed is True

    def test_empty_topic_terms_with_include(self):
        """Test handling of topic with no terms when include is set."""
        config = FilteringConfig(include=["specialterm"])
        filter = TopicFilter(config)

        topic = create_topic(title="Clean Title", terms=[])
        result = filter.filter(topic)

        assert result.passed is False
        assert result.reason == FilterReason.NO_INCLUDE_MATCH


class TestFilterResult:
    """Tests for FilterResult model."""

    def test_result_with_matches(self):
        """Test FilterResult with matched terms."""
        result = FilterResult(
            passed=True,
            matched_terms=["tech", "ai"],
        )

        assert result.passed is True
        assert len(result.matched_terms) == 2

    def test_result_rejected(self):
        """Test FilterResult for rejected topic."""
        result = FilterResult(
            passed=False,
            reason=FilterReason.EXCLUDED_TERM,
        )

        assert result.passed is False
        assert result.matched_terms == []
