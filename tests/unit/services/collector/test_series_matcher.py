"""Unit tests for SeriesMatcher.

Tests cover:
- Basic series matching with keywords and categories
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
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
) -> NormalizedTopic:
    """Create a test NormalizedTopic.

    Note: categories and keywords are lowercased to match
    the behavior of TopicNormalizer.
    """
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


class TestBasicMatching:
    """Tests for basic series matching functionality."""

    def test_match_by_keywords(self):
        """Test matching by keyword overlap."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="ai-news",
                    name="AI 뉴스",
                    criteria=SeriesCriteria(
                        keywords=["ai", "chatgpt", "llm"],
                        min_similarity=0.3,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["ai", "openai", "gpt"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "ai-news"
        assert result.series_name == "AI 뉴스"
        assert "ai" in result.matched_keywords

    def test_match_by_categories(self):
        """Test matching by category overlap."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="tech-review",
                    name="테크 리뷰",
                    criteria=SeriesCriteria(
                        categories=["tech", "gadget", "review"],
                        min_similarity=0.3,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(categories=["tech", "gadget"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "tech-review"
        assert "tech" in result.matched_categories
        assert "gadget" in result.matched_categories

    def test_match_by_keywords_and_categories(self):
        """Test matching using both keywords and categories."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="gaming",
                    name="게임 뉴스",
                    criteria=SeriesCriteria(
                        keywords=["game", "steam", "release"],
                        categories=["gaming", "entertainment"],
                        min_similarity=0.4,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(
            categories=["gaming"],
            keywords=["game", "steam"],
        )
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "gaming"
        assert result.similarity > 0.4

    def test_no_match_below_threshold(self):
        """Test that low similarity doesn't match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="ai-news",
                    name="AI 뉴스",
                    criteria=SeriesCriteria(
                        keywords=["ai", "chatgpt", "llm", "openai", "anthropic"],
                        min_similarity=0.6,  # High threshold
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        # Only 1 out of 5 keywords match = 0.2 similarity
        topic = create_topic(keywords=["ai", "news", "tech"])
        result = matcher.match(topic)

        assert result.matched is False


class TestSimilarityCalculation:
    """Tests for similarity calculation logic."""

    def test_full_keyword_match(self):
        """Test 100% keyword match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b", "c"],
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["a", "b", "c", "d"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 1.0  # All series keywords matched

    def test_partial_keyword_match(self):
        """Test partial keyword match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b", "c", "d"],
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["a", "b"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 0.5  # 2/4 keywords matched

    def test_combined_similarity_average(self):
        """Test that keyword and category similarity are averaged."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b"],  # 2 keywords
                        categories=["x", "y"],  # 2 categories
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        # Match 1/2 keywords (0.5) and 2/2 categories (1.0)
        topic = create_topic(keywords=["a"], categories=["x", "y"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 0.75  # (0.5 + 1.0) / 2

    def test_only_keywords_no_categories(self):
        """Test matching with only keywords defined."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b"],
                        categories=[],  # Empty categories
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["a", "b"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 1.0  # Only keyword similarity used

    def test_only_categories_no_keywords(self):
        """Test matching with only categories defined."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=[],  # Empty keywords
                        categories=["tech", "ai"],
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(categories=["tech"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 0.5  # 1/2 categories matched


class TestBestMatchSelection:
    """Tests for selecting the best match among multiple series."""

    def test_select_highest_similarity(self):
        """Test that highest similarity series is selected."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="series-a",
                    name="Series A",
                    criteria=SeriesCriteria(
                        keywords=["a", "b", "c", "d", "e"],  # 5 keywords
                        min_similarity=0.0,
                    ),
                ),
                SeriesConfig(
                    id="series-b",
                    name="Series B",
                    criteria=SeriesCriteria(
                        keywords=["a", "b"],  # 2 keywords
                        min_similarity=0.0,
                    ),
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        # Topic matches 2 keywords: ["a", "b"]
        # Series A: 2/5 = 0.4
        # Series B: 2/2 = 1.0 (higher)
        topic = create_topic(keywords=["a", "b"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "series-b"
        assert result.similarity == 1.0


class TestScoreBoost:
    """Tests for score boost calculation."""

    def test_score_boost_full_match(self):
        """Test score boost at full similarity."""
        config = SeriesMatcherConfig(
            boost_matched_topics=0.2,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b"],
                        min_similarity=0.0,
                    ),
                )
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["a", "b"])
        result = matcher.match(topic)
        boost = matcher.get_score_boost(result)

        assert result.similarity == 1.0
        assert boost == 0.2  # Full boost at 100% similarity

    def test_score_boost_partial_match(self):
        """Test score boost scales with similarity."""
        config = SeriesMatcherConfig(
            boost_matched_topics=0.2,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["a", "b"],
                        min_similarity=0.0,
                    ),
                )
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["a"])  # 50% match
        result = matcher.match(topic)
        boost = matcher.get_score_boost(result)

        assert result.similarity == 0.5
        assert boost == 0.1  # 50% of 0.2

    def test_score_boost_no_match(self):
        """Test zero boost when no match."""
        config = SeriesMatcherConfig(boost_matched_topics=0.2)
        matcher = SeriesMatcher(config)

        result = SeriesMatchResult(matched=False)
        boost = matcher.get_score_boost(result)

        assert boost == 0.0


class TestEdgeCases:
    """Tests for edge cases and default behavior."""

    def test_empty_config_no_match(self):
        """Test that empty config results in no match."""
        matcher = SeriesMatcher()  # Default empty config

        topic = create_topic(keywords=["anything"])
        result = matcher.match(topic)

        assert result.matched is False

    def test_disabled_matcher_no_match(self):
        """Test that disabled matcher results in no match."""
        config = SeriesMatcherConfig(
            enabled=False,
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(keywords=["test"]),
                )
            ],
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["test"])
        result = matcher.match(topic)

        assert result.matched is False

    def test_disabled_series_skipped(self):
        """Test that disabled series are skipped."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="disabled",
                    name="Disabled",
                    criteria=SeriesCriteria(keywords=["test"]),
                    enabled=False,
                ),
                SeriesConfig(
                    id="enabled",
                    name="Enabled",
                    criteria=SeriesCriteria(keywords=["test"]),
                    enabled=True,
                ),
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["test"])
        result = matcher.match(topic)

        assert result.matched is True
        assert result.series_id == "enabled"

    def test_case_insensitive_matching(self):
        """Test that config values are lowercased for matching."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="test",
                    name="Test",
                    criteria=SeriesCriteria(
                        keywords=["ChatGPT", "OpenAI"],  # Mixed case in config
                        categories=["AI", "Tech"],
                        min_similarity=0.0,
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        # Topic has lowercase (from normalizer)
        topic = create_topic(
            keywords=["chatgpt", "openai"],
            categories=["ai", "tech"],
        )
        result = matcher.match(topic)

        assert result.matched is True
        assert result.similarity == 1.0

    def test_empty_criteria_no_match(self):
        """Test that empty criteria results in no match."""
        config = SeriesMatcherConfig(
            series=[
                SeriesConfig(
                    id="empty",
                    name="Empty",
                    criteria=SeriesCriteria(
                        keywords=[],
                        categories=[],
                    ),
                )
            ]
        )
        matcher = SeriesMatcher(config)

        topic = create_topic(keywords=["test"])
        result = matcher.match(topic)

        # Empty criteria = 0 similarity = no match
        assert result.matched is False


class TestSeriesMatchResult:
    """Tests for SeriesMatchResult model."""

    def test_matched_result(self):
        """Test creating a matched result."""
        result = SeriesMatchResult(
            matched=True,
            series_id="ai-news",
            series_name="AI 뉴스",
            similarity=0.8,
            matched_keywords=["ai", "chatgpt"],
            matched_categories=["tech"],
        )

        assert result.matched is True
        assert result.series_id == "ai-news"
        assert len(result.matched_keywords) == 2

    def test_unmatched_result(self):
        """Test creating an unmatched result."""
        result = SeriesMatchResult(matched=False)

        assert result.matched is False
        assert result.series_id is None
        assert result.similarity == 0.0
        assert result.matched_keywords == []
