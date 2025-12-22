"""Unit tests for SeriesMatcher.

Tests cover:
- Basic series matching with terms
- Similarity calculation
- Score boost calculation
- Edge cases (empty config, disabled series)
"""

import uuid
from datetime import UTC, datetime

from pydantic import HttpUrl

from app.config.series import SeriesConfig, SeriesCriteria, SeriesMatcherConfig
from app.services.collector.base import NormalizedTopic
from app.services.collector.series_matcher import SeriesMatcher, SeriesMatchResult


def create_topic(
    title: str = "Test Topic",
    terms: list[str] | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic.

    Note: terms are lowercased to match the behavior of TopicNormalizer.
    """
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


class TestBasicMatching:
    """Tests for basic series matching functionality."""

    def test_match_by_terms(self):
        """Test matching topic to series by terms."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="ai-news",
                    name="AI 뉴스",
                    criteria=SeriesCriteria(
                        terms=["ai", "chatgpt", "llm"],
                        min_similarity=0.3,  # Lower threshold for testing
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        # Topic has 2/3 matching terms (ai, chatgpt) = 0.66 similarity
        topic = create_topic(terms=["ai", "chatgpt", "openai"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "ai-news"
        assert result.series_name == "AI 뉴스"
        assert "ai" in result.matched_terms

    def test_no_match_below_threshold(self):
        """Test that topics below similarity threshold don't match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="ai-news",
                    name="AI 뉴스",
                    criteria=SeriesCriteria(
                        terms=["ai", "chatgpt", "llm", "openai", "anthropic"],
                        min_similarity=0.5,
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        # Only 1 out of 5 terms match = 0.2 similarity
        topic = create_topic(terms=["ai", "news", "tech"])
        result = matcher.match(topic)

        assert result.matched is False


class TestSimilarityCalculation:
    """Tests for similarity calculation."""

    def test_full_match_similarity(self):
        """Test 100% similarity when all series terms match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        terms=["a", "b", "c"],
                        min_similarity=0.5,
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["a", "b", "c", "d"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 1.0  # All series terms matched

    def test_partial_match_similarity(self):
        """Test partial similarity calculation."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        terms=["a", "b", "c", "d"],
                        min_similarity=0.4,
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["a", "b"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 0.5  # 2/4 terms matched


class TestBestMatchSelection:
    """Tests for selecting best match among multiple series."""

    def test_higher_similarity_wins(self):
        """Test that series with higher similarity is selected."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="low-match",
                    name="Low Match",
                    criteria=SeriesCriteria(
                        terms=["a", "b", "c", "d", "e"],  # 5 terms
                        min_similarity=0.3,
                    ),
                ),
                SeriesConfig(
                    id="high-match",
                    name="High Match",
                    criteria=SeriesCriteria(
                        terms=["a", "b"],  # 2 terms
                        min_similarity=0.5,
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        # Topic matches 2 terms: ["a", "b"]
        # Low match: 2/5 = 0.4
        # High match: 2/2 = 1.0
        topic = create_topic(terms=["a", "b"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "high-match"
        assert result.similarity == 1.0


class TestConfigOptions:
    """Tests for configuration options."""

    def test_disabled_series_not_matched(self):
        """Test that disabled series are not matched."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="disabled",
                    name="Disabled Series",
                    enabled=False,
                    criteria=SeriesCriteria(terms=["test"]),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["test"])
        result = matcher.match(topic)

        assert result.matched is False

    def test_enabled_series_checked(self):
        """Test that enabled series are checked."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="disabled",
                    name="Disabled",
                    enabled=False,
                    criteria=SeriesCriteria(terms=["test"]),
                ),
                SeriesConfig(
                    id="enabled",
                    name="Enabled",
                    enabled=True,
                    criteria=SeriesCriteria(terms=["test"]),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["test"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "enabled"

    def test_case_insensitive_matching(self):
        """Test case-insensitive term matching."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="ai-news",
                    name="AI News",
                    criteria=SeriesCriteria(
                        terms=["ChatGPT", "OpenAI"],  # Mixed case in config
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        # Topic terms are lowercase (normalized)
        topic = create_topic(terms=["chatgpt", "openai"])
        result = matcher.match(topic)

        assert result.matched is True

    def test_empty_terms_no_match(self):
        """Test that series with no terms don't match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="empty",
                    name="Empty",
                    criteria=SeriesCriteria(terms=[]),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["test"])
        result = matcher.match(topic)

        assert result.matched is False

    def test_matcher_disabled(self):
        """Test that disabled matcher returns no match."""
        config = SeriesMatcherConfig(
            enabled=False,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(terms=["test"]),
                ),
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["test"])
        result = matcher.match(topic)

        assert result.matched is False

    def test_no_series_configured(self):
        """Test matching with no series configured."""
        config = SeriesMatcherConfig(series=[])
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["anything"])
        result = matcher.match(topic)

        assert result.matched is False


class TestScoreBoost:
    """Tests for score boost calculation."""

    def test_boost_for_matched_series(self):
        """Test score boost for matched series."""
        config = SeriesMatcherConfig(
            boost_matched_topics=0.2,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(terms=["a", "b"]),
                ),
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["a", "b"])
        match_result = matcher.match(topic)

        # Full similarity (1.0) * boost (0.2) = 0.2
        boost = matcher.get_score_boost(match_result)
        assert boost == 0.2

    def test_boost_scaled_by_similarity(self):
        """Test that boost is scaled by match similarity."""
        config = SeriesMatcherConfig(
            boost_matched_topics=0.2,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        terms=["a", "b"],
                        min_similarity=0.4,
                    ),
                ),
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(terms=["a"])  # 50% match
        match_result = matcher.match(topic)

        # Half similarity (0.5) * boost (0.2) = 0.1
        boost = matcher.get_score_boost(match_result)
        assert boost == 0.1

    def test_no_boost_for_unmatched(self):
        """Test zero boost for unmatched topics."""
        matcher = SeriesMatcher(SeriesMatcherConfig())

        result = SeriesMatchResult(matched=False)
        boost = matcher.get_score_boost(result)

        assert boost == 0.0


class TestSeriesMatchResult:
    """Tests for SeriesMatchResult model."""

    def test_result_with_matches(self):
        """Test SeriesMatchResult with matched terms."""
        result = SeriesMatchResult(
            matched=True,
            series_id="test",
            series_name="Test Series",
            similarity=0.8,
            matched_terms=["ai", "chatgpt"],
        )

        assert result.matched is True
        assert len(result.matched_terms) == 2

    def test_result_not_matched(self):
        """Test SeriesMatchResult for unmatched topic."""
        result = SeriesMatchResult(matched=False)

        assert result.matched is False
        assert result.matched_terms == []
