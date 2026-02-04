"""Unit tests for collector base module."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.services.collector.base import (
    CollectionResult,
    NormalizedTopic,
    RawTopic,
    ScoredTopic,
)


class TestRawTopic:
    """Tests for RawTopic DTO."""

    def test_minimal_raw_topic(self):
        """Test creating RawTopic with minimal fields."""
        topic = RawTopic(
            source_id="test-source",
            source_url="https://example.com/topic",
            title="Test Topic Title",
        )

        assert topic.source_id == "test-source"
        assert str(topic.source_url) == "https://example.com/topic"
        assert topic.title == "Test Topic Title"
        assert topic.content is None
        assert topic.published_at is None
        assert topic.metrics == {}
        assert topic.metadata == {}

    def test_full_raw_topic(self):
        """Test creating RawTopic with all fields."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        topic = RawTopic(
            source_id="reddit-123",
            source_url="https://reddit.com/r/test/123",
            title="Breaking: AI News",
            content="Full article content here...",
            published_at=published,
            metrics={"upvotes": 1500, "comments": 234},
            metadata={"subreddit": "technology"},
        )

        assert topic.content == "Full article content here..."
        assert topic.published_at == published
        assert topic.metrics["upvotes"] == 1500
        assert topic.metadata["subreddit"] == "technology"

    def test_invalid_url_raises(self):
        """Test that invalid URL raises validation error."""
        with pytest.raises(ValidationError):
            RawTopic(
                source_id="test",
                source_url="not-a-valid-url",
                title="Test",
            )


class TestNormalizedTopic:
    """Tests for NormalizedTopic DTO."""

    def test_minimal_normalized_topic(self):
        """Test creating NormalizedTopic with minimal fields."""
        source_id = uuid.uuid4()
        topic = NormalizedTopic(
            source_id=source_id,
            source_url="https://example.com/topic",
            title_original="Test Topic",
            title_normalized="test topic",
            summary="A brief summary",
            content_hash="abc123" * 10 + "abcd",  # 64 char hash
        )

        assert topic.source_id == source_id
        assert topic.title_original == "Test Topic"
        assert topic.title_normalized == "test topic"
        assert topic.summary == "A brief summary"
        assert topic.title_translated is None
        assert topic.terms == []
        assert topic.entities == {}
        assert topic.language == "en"

    def test_full_normalized_topic(self):
        """Test creating NormalizedTopic with all fields."""
        source_id = uuid.uuid4()
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        topic = NormalizedTopic(
            source_id=source_id,
            source_url="https://example.com/topic",
            title_original="AI Breaking News",
            title_translated="AI 속보",
            title_normalized="ai breaking news",
            summary="AI 관련 최신 뉴스 요약",
            terms=["ai", "machine learning", "technology"],
            entities={"companies": ["OpenAI", "Anthropic"], "products": ["GPT-5"]},
            language="en",
            published_at=published,
            content_hash="abc123" * 10 + "abcd",
            metrics={"upvotes": 500},
            metadata={"source_name": "reddit"},
        )

        assert topic.title_translated == "AI 속보"
        assert "ai" in topic.terms
        assert "OpenAI" in topic.entities["companies"]
        assert topic.metrics["upvotes"] == 500

    def test_normalized_topic_with_korean(self):
        """Test NormalizedTopic with Korean content."""
        topic = NormalizedTopic(
            source_id=uuid.uuid4(),
            source_url="https://example.com/topic",
            title_original="클로드 3.5 발표",
            title_normalized="클로드 3.5 발표",
            summary="앤트로픽이 클로드 3.5를 발표했습니다",
            language="ko",
            content_hash="hash" * 16,
        )

        assert topic.language == "ko"
        assert "클로드" in topic.title_original


class TestScoredTopic:
    """Tests for ScoredTopic DTO."""

    def test_scored_topic(self):
        """Test creating ScoredTopic with scores."""
        topic = ScoredTopic(
            source_id=uuid.uuid4(),
            source_url="https://example.com/topic",
            title_original="Test Topic",
            title_normalized="test topic",
            summary="Summary",
            content_hash="hash" * 16,
            score_source=0.8,
            score_freshness=0.9,
            score_trend=0.7,
            score_relevance=0.85,
            score_total=85,
        )

        assert topic.score_source == 0.8
        assert topic.score_freshness == 0.9
        assert topic.score_trend == 0.7
        assert topic.score_relevance == 0.85
        assert topic.score_total == 85

    def test_score_boundaries(self):
        """Test score validation at boundaries."""
        # Minimum scores
        topic_min = ScoredTopic(
            source_id=uuid.uuid4(),
            source_url="https://example.com/topic",
            title_original="Test",
            title_normalized="test",
            summary="Summary",
            content_hash="hash" * 16,
            score_source=0.0,
            score_freshness=0.0,
            score_trend=0.0,
            score_relevance=0.0,
            score_total=0,
        )
        assert topic_min.score_total == 0

        # Maximum scores
        topic_max = ScoredTopic(
            source_id=uuid.uuid4(),
            source_url="https://example.com/topic",
            title_original="Test",
            title_normalized="test",
            summary="Summary",
            content_hash="hash" * 16,
            score_source=1.0,
            score_freshness=1.0,
            score_trend=1.0,
            score_relevance=1.0,
            score_total=100,
        )
        assert topic_max.score_total == 100

    def test_score_out_of_range_raises(self):
        """Test that out-of-range scores raise validation error."""
        with pytest.raises(ValidationError):
            ScoredTopic(
                source_id=uuid.uuid4(),
                source_url="https://example.com/topic",
                title_original="Test",
                title_normalized="test",
                summary="Summary",
                content_hash="hash" * 16,
                score_source=1.5,  # Invalid: > 1.0
                score_freshness=0.5,
                score_trend=0.5,
                score_relevance=0.5,
                score_total=50,
            )

    def test_total_score_out_of_range_raises(self):
        """Test that total score > 100 raises validation error."""
        with pytest.raises(ValidationError):
            ScoredTopic(
                source_id=uuid.uuid4(),
                source_url="https://example.com/topic",
                title_original="Test",
                title_normalized="test",
                summary="Summary",
                content_hash="hash" * 16,
                score_source=0.5,
                score_freshness=0.5,
                score_trend=0.5,
                score_relevance=0.5,
                score_total=101,  # Invalid: > 100
            )


class TestCollectionResult:
    """Tests for CollectionResult DTO."""

    def test_minimal_collection_result(self):
        """Test creating CollectionResult with minimal fields."""
        source_id = uuid.uuid4()
        result = CollectionResult(
            source_id=source_id,
            source_name="reddit",
        )

        assert result.source_id == source_id
        assert result.source_name == "reddit"
        assert result.collected_count == 0
        assert result.normalized_count == 0
        assert result.deduplicated_count == 0
        assert result.scored_count == 0
        assert result.added_to_queue == 0
        assert result.errors == []
        assert result.duration_seconds == 0.0

    def test_full_collection_result(self):
        """Test creating CollectionResult with all fields."""
        source_id = uuid.uuid4()
        result = CollectionResult(
            source_id=source_id,
            source_name="hackernews",
            collected_count=100,
            normalized_count=95,
            deduplicated_count=80,
            scored_count=80,
            added_to_queue=75,
            errors=["Failed to parse item 3", "Network timeout for item 7"],
            duration_seconds=12.5,
        )

        assert result.collected_count == 100
        assert result.normalized_count == 95
        assert result.deduplicated_count == 80
        assert result.scored_count == 80
        assert result.added_to_queue == 75
        assert len(result.errors) == 2
        assert result.duration_seconds == 12.5

    def test_collection_result_with_errors(self):
        """Test CollectionResult with partial success."""
        result = CollectionResult(
            source_id=uuid.uuid4(),
            source_name="rss",
            collected_count=50,
            normalized_count=45,
            deduplicated_count=40,
            scored_count=35,
            added_to_queue=30,
            errors=["5 items failed normalization"],
        )

        assert result.collected_count > result.normalized_count
        assert result.normalized_count > result.deduplicated_count
        assert len(result.errors) == 1
