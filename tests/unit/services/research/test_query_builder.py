"""Unit tests for ResearchQueryBuilder."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.research import QueryStrategy, ResearchConfig
from app.prompts.manager import LLMSettings
from app.services.collector.base import ScoredTopic
from app.services.collector.clusterer import TopicCluster
from app.services.research.query_builder import ResearchQueryBuilder


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create mock LLM client."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "AI generated query 1\nAI query 2"
    client.complete = AsyncMock(return_value=mock_response)
    return client


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock prompt manager."""
    manager = MagicMock()
    manager.render.return_value = "Mocked prompt for research query"
    manager.get_llm_settings.return_value = LLMSettings(
        model="anthropic/claude-3-5-haiku-20241022",
        max_tokens=200,
        temperature=0.3,
    )
    return manager


@pytest.fixture
def query_builder(
    mock_llm_client: MagicMock, mock_prompt_manager: MagicMock
) -> ResearchQueryBuilder:
    """Create query builder with mock LLM and prompt manager."""
    return ResearchQueryBuilder(llm_client=mock_llm_client, prompt_manager=mock_prompt_manager)


@pytest.fixture
def sample_topic() -> ScoredTopic:
    """Create a sample scored topic."""
    return ScoredTopic(
        source_id="00000000-0000-0000-0000-000000000001",
        source_url="https://example.com/article",
        title_original="OpenAI announces GPT-5 with revolutionary capabilities",
        title_normalized="openai announces gpt-5 with revolutionary capabilities",
        summary="OpenAI has unveiled GPT-5, their latest AI model.",
        terms=["openai", "gpt-5", "ai", "language model", "artificial intelligence"],
        entities={"company": ["OpenAI"], "product": ["GPT-5"]},
        language="en",
        content_hash="abc123",
        metrics={"score": 100},
        metadata={"source_name": "tech_news"},
        score_source=0.8,
        score_freshness=0.9,
        score_trend=0.7,
        score_relevance=0.85,
        score_total=85,
    )


@pytest.fixture
def sample_cluster(sample_topic: ScoredTopic) -> TopicCluster:
    """Create a sample topic cluster."""
    related = ScoredTopic(
        source_id="00000000-0000-0000-0000-000000000002",
        source_url="https://other.com/news",
        title_original="New AI breakthrough from OpenAI",
        title_normalized="new ai breakthrough from openai",
        summary="Latest developments in AI.",
        terms=["ai", "openai", "breakthrough", "machine learning"],
        entities={"company": ["OpenAI"]},
        language="en",
        content_hash="def456",
        metrics={"score": 80},
        metadata={"source_name": "ai_news"},
        score_source=0.7,
        score_freshness=0.8,
        score_trend=0.6,
        score_relevance=0.75,
        score_total=75,
    )

    return TopicCluster(
        primary_topic=sample_topic,
        related_topics=[related],
        sources={"tech_news", "ai_news"},
        combined_terms=["openai", "gpt-5", "ai", "language model", "breakthrough"],
        total_engagement=180,
        coverage_score=0.5,
    )


@pytest.mark.asyncio
async def test_build_queries_keyword_strategy(
    query_builder: ResearchQueryBuilder,
    sample_cluster: TopicCluster,
) -> None:
    """Test keyword strategy builds queries from terms."""
    config = ResearchConfig(
        query_strategy=QueryStrategy.KEYWORD,
        max_queries=3,
    )

    queries = await query_builder.build_queries(sample_cluster, config)

    assert len(queries) <= 3
    assert all(isinstance(q, str) for q in queries)
    assert all(len(q) > 0 for q in queries)


@pytest.mark.asyncio
async def test_build_queries_title_strategy(
    query_builder: ResearchQueryBuilder,
    sample_cluster: TopicCluster,
) -> None:
    """Test title strategy uses normalized title."""
    config = ResearchConfig(
        query_strategy=QueryStrategy.TITLE,
        max_queries=2,
    )

    queries = await query_builder.build_queries(sample_cluster, config)

    assert len(queries) >= 1
    assert sample_cluster.primary_topic.title_normalized in queries[0]


@pytest.mark.asyncio
async def test_build_queries_llm_strategy(
    query_builder: ResearchQueryBuilder,
    sample_cluster: TopicCluster,
    mock_llm_client: MagicMock,
) -> None:
    """Test LLM strategy generates queries via LLM."""
    config = ResearchConfig(
        query_strategy=QueryStrategy.LLM,
        max_queries=3,
    )

    queries = await query_builder.build_queries(sample_cluster, config)

    mock_llm_client.complete.assert_called_once()
    assert len(queries) <= 3


@pytest.mark.asyncio
async def test_build_queries_limits_results(
    query_builder: ResearchQueryBuilder,
    sample_cluster: TopicCluster,
) -> None:
    """Test query count is limited by config."""
    config = ResearchConfig(
        query_strategy=QueryStrategy.KEYWORD,
        max_queries=1,
    )

    queries = await query_builder.build_queries(sample_cluster, config)

    assert len(queries) <= 1


@pytest.mark.asyncio
async def test_build_queries_empty_terms(
    query_builder: ResearchQueryBuilder,
) -> None:
    """Test handling of cluster with no terms."""
    topic = ScoredTopic(
        source_id="00000000-0000-0000-0000-000000000001",
        source_url="https://example.com/article",
        title_original="Test Title",
        title_normalized="test title",
        summary="Test summary",
        terms=[],
        entities={},
        language="en",
        content_hash="abc123",
        metrics={},
        metadata={},
        score_source=0.5,
        score_freshness=0.5,
        score_trend=0.5,
        score_relevance=0.5,
        score_total=50,
    )

    cluster = TopicCluster(
        primary_topic=topic,
        sources={"test"},
        combined_terms=[],
    )

    config = ResearchConfig(
        query_strategy=QueryStrategy.KEYWORD,
        max_queries=3,
    )

    queries = await query_builder.build_queries(cluster, config)

    # Should fall back to title when no terms
    assert len(queries) >= 1
    assert "test title" in queries[0].lower()


@pytest.mark.asyncio
async def test_build_queries_title_strategy_with_related(
    query_builder: ResearchQueryBuilder,
    sample_cluster: TopicCluster,
) -> None:
    """Test title strategy includes related topic titles."""
    config = ResearchConfig(
        query_strategy=QueryStrategy.TITLE,
        max_queries=3,
    )

    queries = await query_builder.build_queries(sample_cluster, config)

    # Should include both primary and related titles
    assert len(queries) >= 1
    assert sample_cluster.primary_topic.title_normalized in queries[0]
    # With max_queries=3, related topics should be included
    if len(sample_cluster.related_topics) > 0:
        assert len(queries) >= 2
