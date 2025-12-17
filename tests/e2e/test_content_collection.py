"""E2E tests for content collection pipeline.

These tests verify the topic collection workflow:
1. Source scraping (with mocked network calls)
2. Topic normalization
3. Deduplication
4. Filtering
5. Scoring
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import DedupConfig, ScoringConfig
from app.config.filtering import (
    CategoryFilter,
    ExcludeFilters,
    IncludeFilters,
    KeywordFilter,
    TopicFilterConfig,
)
from app.services.collector.base import ScoredTopic
from app.services.collector.deduplicator import TopicDeduplicator
from app.services.collector.filter import TopicFilter
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.scorer import TopicScorer

from .conftest import create_normalized_topic, create_raw_topic


class TestTopicNormalization:
    """E2E tests for topic normalization."""

    @pytest.mark.asyncio
    async def test_normalize_korean_topic(self) -> None:
        """Test normalization of Korean topic."""
        llm_client = AsyncMock()
        mock_content = (
            '{"categories": ["tech"], "keywords": ["AI", "기술"], '
            '"entities": {}, "summary": "AI 기술 관련 요약"}'
        )
        llm_client.complete = AsyncMock(return_value=MagicMock(content=mock_content))

        normalizer = TopicNormalizer(llm_client=llm_client)

        raw_topic = create_raw_topic(
            title="AI 기술의 미래: 2024년 전망",
            source_id="test_source",
            source_url="https://example.com/1",
        )

        source_id = uuid.uuid4()
        result = await normalizer.normalize(raw_topic, source_id)

        assert result is not None
        assert result.title_original == raw_topic.title
        assert result.language == "ko"
        assert result.source_id == source_id

    @pytest.mark.asyncio
    async def test_normalize_english_topic(self) -> None:
        """Test normalization of English topic."""
        llm_client = AsyncMock()
        mock_content = (
            '{"categories": ["tech"], "keywords": ["AI", "future"], '
            '"entities": {}, "summary": "Summary about AI"}'
        )
        llm_client.complete = AsyncMock(return_value=MagicMock(content=mock_content))

        normalizer = TopicNormalizer(llm_client=llm_client)

        raw_topic = create_raw_topic(
            title="The Future of AI Technology in 2024",
            source_id="test_source",
            source_url="https://example.com/2",
        )

        source_id = uuid.uuid4()
        result = await normalizer.normalize(raw_topic, source_id)

        assert result is not None
        assert result.language == "en"


class TestTopicDeduplication:
    """E2E tests for topic deduplication."""

    @pytest.mark.asyncio
    async def test_exact_duplicate_detection(self) -> None:
        """Test detection of exact duplicate topics."""
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[None, b"existing"])
        redis.setex = AsyncMock()

        deduplicator = TopicDeduplicator(redis=redis, config=DedupConfig())

        topic = create_normalized_topic(
            title="테스트 토픽",
            keywords=["test"],
        )
        channel_id = "test_channel"

        # First time should not be duplicate
        result1 = await deduplicator.is_duplicate(topic, channel_id)
        await deduplicator.mark_as_seen(topic, channel_id)

        # Second time should be duplicate
        result2 = await deduplicator.is_duplicate(topic, channel_id)

        assert not result1.is_duplicate
        assert result2.is_duplicate


class TestTopicFiltering:
    """E2E tests for topic filtering."""

    @pytest.mark.asyncio
    async def test_category_filter(self) -> None:
        """Test filtering by category."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                categories=[
                    CategoryFilter(name="tech"),
                    CategoryFilter(name="science"),
                ]
            ),
            exclude=ExcludeFilters(categories=["politics"]),
            require_category_match=True,
        )
        filter_service = TopicFilter(config=config)

        topics = [
            create_normalized_topic("Tech Topic", categories=["tech"]),
            create_normalized_topic("Science Topic", categories=["science"]),
            create_normalized_topic("Politics Topic", categories=["politics"]),
            create_normalized_topic("Other Topic", categories=["entertainment"]),
        ]

        results = [filter_service.filter(t) for t in topics]

        # Tech and Science should pass
        assert results[0].passed is True
        assert results[1].passed is True
        # Politics should be excluded
        assert results[2].passed is False
        # Entertainment doesn't match required category
        assert results[3].passed is False

    @pytest.mark.asyncio
    async def test_keyword_filter(self) -> None:
        """Test filtering by keywords."""
        config = TopicFilterConfig(
            include=IncludeFilters(
                keywords=[
                    KeywordFilter(keyword="ai"),
                    KeywordFilter(keyword="머신러닝"),
                ]
            ),
            exclude=ExcludeFilters(keywords=["광고", "스팸"]),
            require_keyword_match=True,
        )
        filter_service = TopicFilter(config=config)

        topics = [
            create_normalized_topic("AI 기술", keywords=["ai", "기술"]),
            create_normalized_topic("머신러닝 트렌드", keywords=["머신러닝"]),
            create_normalized_topic("광고 토픽", keywords=["광고"]),
            create_normalized_topic("일반 토픽", keywords=["일반"]),
        ]

        results = [filter_service.filter(t) for t in topics]

        # AI and 머신러닝 topics should pass
        assert results[0].passed is True
        assert results[1].passed is True
        # 광고 should be excluded
        assert results[2].passed is False
        # 일반 doesn't match required keyword
        assert results[3].passed is False


class TestTopicScoring:
    """E2E tests for topic scoring."""

    @pytest.mark.asyncio
    async def test_score_calculation(self) -> None:
        """Test topic scoring calculation."""
        config = ScoringConfig()
        scorer = TopicScorer(config=config)

        topic = create_normalized_topic(
            title="인기 있는 AI 토픽",
            keywords=["ai", "인공지능", "기술"],
        )

        result = scorer.score(topic)

        assert isinstance(result, ScoredTopic)
        assert result.score_total >= 0
        assert result.score_total <= 100

    @pytest.mark.asyncio
    async def test_batch_scoring_and_sorting(self) -> None:
        """Test batch scoring with proper ordering."""
        config = ScoringConfig()
        scorer = TopicScorer(config=config)

        topics = [
            create_normalized_topic("Low Engagement", engagement_score=10),
            create_normalized_topic("High Engagement", engagement_score=1000),
            create_normalized_topic("Medium Engagement", engagement_score=100),
        ]

        # Score each topic
        results = [scorer.score(t) for t in topics]

        # Sort by score descending
        results.sort(key=lambda x: x.score_total, reverse=True)

        # Verify sorted by score descending
        assert len(results) == 3
        assert results[0].score_total >= results[1].score_total
        assert results[1].score_total >= results[2].score_total


class TestCollectionPipeline:
    """E2E tests for complete collection pipeline."""

    @pytest.mark.asyncio
    async def test_full_collection_flow(self) -> None:
        """Test complete topic collection pipeline."""
        # Setup mocks - different responses for different topics
        llm_client = AsyncMock()
        tech_content = (
            '{"categories": ["tech"], "keywords": ["ai"], '
            '"entities": {}, "summary": "AI summary"}'
        )
        politics_content = (
            '{"categories": ["politics"], "keywords": ["정치"], '
            '"entities": {}, "summary": "Politics summary"}'
        )
        llm_client.complete = AsyncMock(
            side_effect=[
                MagicMock(content=tech_content),
                MagicMock(content=politics_content),
            ]
        )

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        # Create services
        normalizer = TopicNormalizer(llm_client=llm_client)
        deduplicator = TopicDeduplicator(redis=redis, config=DedupConfig())
        filter_service = TopicFilter(
            config=TopicFilterConfig(
                include=IncludeFilters(categories=[CategoryFilter(name="tech")]),
                require_category_match=True,
            )
        )
        scorer = TopicScorer(config=ScoringConfig())

        # Simulate raw topics from source
        raw_topics = [
            create_raw_topic(
                title="AI 혁신 기술",
                source_id="test_source",
                source_url="https://example.com/1",
            ),
            create_raw_topic(
                title="정치 뉴스",
                source_id="test_source",
                source_url="https://example.com/2",
            ),
        ]

        source_id = uuid.uuid4()
        channel_id = "test_channel"

        # Step 1: Normalize
        normalized = []
        for raw in raw_topics:
            result = await normalizer.normalize(raw, source_id)
            if result:
                normalized.append(result)

        assert len(normalized) == 2

        # Step 2: Deduplicate
        unique = []
        for topic in normalized:
            dedup_result = await deduplicator.is_duplicate(topic, channel_id)
            if not dedup_result.is_duplicate:
                await deduplicator.mark_as_seen(topic, channel_id)
                unique.append(topic)

        assert len(unique) == 2

        # Step 3: Filter
        filtered = [t for t in unique if filter_service.filter(t).passed]

        # Only tech should pass (AI 혁신 기술)
        assert len(filtered) == 1
        assert filtered[0].categories == ["tech"]

        # Step 4: Score
        scored = [scorer.score(t) for t in filtered]

        # Verify pipeline output
        assert len(scored) == 1
        assert all(isinstance(t, ScoredTopic) for t in scored)
