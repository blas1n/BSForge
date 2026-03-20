"""E2E tests for content collection pipeline.

These tests verify the topic collection workflow:
1. Source scraping (with mocked network calls)
2. Topic normalization
3. Filtering
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.filtering import FilteringConfig
from app.services.collector.filter import TopicFilter
from app.services.collector.normalizer import TopicNormalizer

from .conftest import create_normalized_topic, create_raw_topic


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock prompt manager for tests."""
    manager = MagicMock()
    manager.render.return_value = "Mocked prompt"
    return manager


class TestTopicNormalization:
    """E2E tests for topic normalization."""

    @pytest.mark.asyncio
    async def test_normalize_korean_topic(self, mock_prompt_manager: MagicMock) -> None:
        """Test normalization of Korean topic."""
        llm_client = AsyncMock()
        mock_content = (
            '{"terms": ["tech", "AI", "기술"], "entities": {}, "summary": "AI 기술 관련 요약"}'
        )
        llm_client.complete = AsyncMock(return_value=MagicMock(content=mock_content))

        normalizer = TopicNormalizer(llm_client=llm_client, prompt_manager=mock_prompt_manager)

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
    async def test_normalize_english_topic(self, mock_prompt_manager: MagicMock) -> None:
        """Test normalization of English topic."""
        llm_client = AsyncMock()
        mock_content = (
            '{"terms": ["tech", "AI", "future"], "entities": {}, "summary": "Summary about AI"}'
        )
        llm_client.complete = AsyncMock(return_value=MagicMock(content=mock_content))

        normalizer = TopicNormalizer(llm_client=llm_client, prompt_manager=mock_prompt_manager)

        raw_topic = create_raw_topic(
            title="The Future of AI Technology in 2024",
            source_id="test_source",
            source_url="https://example.com/2",
        )

        source_id = uuid.uuid4()
        result = await normalizer.normalize(raw_topic, source_id)

        assert result is not None
        assert result.language == "en"


class TestTopicFiltering:
    """E2E tests for topic filtering."""

    @pytest.mark.asyncio
    async def test_term_include_filter(self) -> None:
        """Test filtering by include terms."""
        config = FilteringConfig(
            include=["tech", "science"],
            exclude=["politics"],
        )
        filter_service = TopicFilter(config=config)

        topics = [
            create_normalized_topic("Tech Topic", terms=["tech", "innovation"]),
            create_normalized_topic("Science Topic", terms=["science", "research"]),
            create_normalized_topic("Politics Topic", terms=["politics", "news"]),
            create_normalized_topic("Other Topic", terms=["entertainment"]),
        ]

        results = [filter_service.filter(t) for t in topics]

        # Tech and Science should pass (include match)
        assert results[0].passed is True
        assert results[1].passed is True
        # Politics should be excluded
        assert results[2].passed is False
        # Entertainment doesn't match required include terms
        assert results[3].passed is False

    @pytest.mark.asyncio
    async def test_term_exclude_filter(self) -> None:
        """Test filtering by exclude terms."""
        config = FilteringConfig(
            include=["ai", "머신러닝"],
            exclude=["광고", "스팸"],
        )
        filter_service = TopicFilter(config=config)

        topics = [
            create_normalized_topic("AI 기술", terms=["ai", "기술"]),
            create_normalized_topic("머신러닝 트렌드", terms=["머신러닝"]),
            create_normalized_topic("광고 토픽", terms=["광고"]),
            create_normalized_topic("일반 토픽", terms=["일반"]),
        ]

        results = [filter_service.filter(t) for t in topics]

        # AI and 머신러닝 topics should pass
        assert results[0].passed is True
        assert results[1].passed is True
        # 광고 should be excluded
        assert results[2].passed is False
        # 일반 doesn't match required include terms
        assert results[3].passed is False


class TestCollectionPipeline:
    """E2E tests for collection pipeline steps."""

    @pytest.mark.asyncio
    async def test_normalize_and_filter_flow(self, mock_prompt_manager: MagicMock) -> None:
        """Test normalization followed by filtering."""
        llm_client = AsyncMock()
        tech_content = '{"terms": ["ai", "tech"], "entities": {}, "summary": "AI summary"}'
        llm_client.complete = AsyncMock(return_value=MagicMock(content=tech_content))

        # Create raw topic
        raw_topic = create_raw_topic(
            title="AI Technology 2024",
            source_id="tech_source",
            source_url="https://example.com/tech/1",
        )

        # Step 1: Normalize
        normalizer = TopicNormalizer(llm_client=llm_client, prompt_manager=mock_prompt_manager)
        source_id = uuid.uuid4()
        normalized = await normalizer.normalize(raw_topic, source_id)
        assert normalized is not None

        # Step 2: Filter
        topic_filter = TopicFilter(config=FilteringConfig(include=["ai"], exclude=["spam"]))
        filter_result = topic_filter.filter(normalized)
        assert filter_result.passed
