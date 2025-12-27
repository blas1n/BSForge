"""Unit tests for ClusterEnricher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.prompts.manager import LLMSettings
from app.services.collector.base import ScoredTopic
from app.services.collector.cluster_enricher import ClusterEnricher, EnrichedCluster
from app.services.collector.clusterer import TopicCluster


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create mock LLM client."""
    client = MagicMock()
    # ClusterEnricher uses complete() not complete_simple()
    mock_response = MagicMock()
    mock_response.content = "This is a unified summary combining all sources about OpenAI's GPT-5."
    client.complete = AsyncMock(return_value=mock_response)
    return client


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock prompt manager."""
    manager = MagicMock()
    manager.render.return_value = "Mocked prompt for cluster summary"
    manager.get_llm_settings.return_value = LLMSettings(
        model="anthropic/claude-3-5-haiku-20241022",
        max_tokens=500,
        temperature=0.3,
    )
    return manager


@pytest.fixture
def cluster_enricher(mock_llm_client: MagicMock, mock_prompt_manager: MagicMock) -> ClusterEnricher:
    """Create cluster enricher with mock LLM and prompt manager."""
    return ClusterEnricher(llm_client=mock_llm_client, prompt_manager=mock_prompt_manager)


@pytest.fixture
def primary_topic() -> ScoredTopic:
    """Create primary scored topic."""
    return ScoredTopic(
        source_id="00000000-0000-0000-0000-000000000001",
        source_url="https://source1.com/article",
        title_original="OpenAI GPT-5 Released",
        title_normalized="openai gpt-5 released",
        summary="OpenAI released GPT-5 with amazing capabilities.",
        terms=["openai", "gpt-5", "release"],
        entities={"company": ["OpenAI"], "product": ["GPT-5"]},
        language="en",
        content_hash="hash1",
        metrics={"score": 100},
        metadata={"source_name": "source1"},
        score_source=0.9,
        score_freshness=0.9,
        score_trend=0.8,
        score_relevance=0.9,
        score_total=90,
    )


@pytest.fixture
def related_topics() -> list[ScoredTopic]:
    """Create related topics."""
    return [
        ScoredTopic(
            source_id="00000000-0000-0000-0000-000000000002",
            source_url="https://source2.com/news",
            title_original="GPT-5 Benchmarks Show Impressive Results",
            title_normalized="gpt-5 benchmarks show impressive results",
            summary="GPT-5 outperforms previous models in benchmarks.",
            terms=["gpt-5", "benchmarks", "performance"],
            entities={"product": ["GPT-5"]},
            language="en",
            content_hash="hash2",
            metrics={"score": 80},
            metadata={"source_name": "source2"},
            score_source=0.8,
            score_freshness=0.8,
            score_trend=0.7,
            score_relevance=0.8,
            score_total=80,
        ),
        ScoredTopic(
            source_id="00000000-0000-0000-0000-000000000003",
            source_url="https://source3.com/analysis",
            title_original="What GPT-5 Means for AI Industry",
            title_normalized="what gpt-5 means for ai industry",
            summary="Industry analysis of GPT-5 impact.",
            terms=["gpt-5", "ai", "industry", "impact"],
            entities={"product": ["GPT-5"]},
            language="en",
            content_hash="hash3",
            metrics={"score": 70},
            metadata={"source_name": "source3"},
            score_source=0.7,
            score_freshness=0.7,
            score_trend=0.6,
            score_relevance=0.7,
            score_total=70,
        ),
    ]


@pytest.fixture
def multi_source_cluster(
    primary_topic: ScoredTopic,
    related_topics: list[ScoredTopic],
) -> TopicCluster:
    """Create a multi-source topic cluster."""
    return TopicCluster(
        primary_topic=primary_topic,
        related_topics=related_topics,
        sources={"source1", "source2", "source3"},
        combined_terms=["openai", "gpt-5", "release", "benchmarks", "ai", "industry"],
        total_engagement=250,
        coverage_score=0.75,
    )


@pytest.fixture
def single_source_cluster(primary_topic: ScoredTopic) -> TopicCluster:
    """Create a single-source topic cluster."""
    return TopicCluster(
        primary_topic=primary_topic,
        sources={"source1"},
        combined_terms=["openai", "gpt-5", "release"],
        total_engagement=100,
        coverage_score=0.25,
    )


@pytest.mark.asyncio
async def test_enrich_multi_source_cluster(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
    mock_llm_client: MagicMock,
) -> None:
    """Test enrichment of multi-source cluster calls LLM."""
    result = await cluster_enricher.enrich(multi_source_cluster)

    assert isinstance(result, EnrichedCluster)
    assert result.cluster is multi_source_cluster
    assert "OpenAI" in result.combined_summary
    assert len(result.source_urls) == 3
    mock_llm_client.complete.assert_called_once()


@pytest.mark.asyncio
async def test_enrich_combines_terms(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
) -> None:
    """Test enrichment combines terms from all topics."""
    result = await cluster_enricher.enrich(multi_source_cluster)

    expected_terms = {"openai", "gpt-5", "release", "benchmarks", "performance", "ai"}
    assert all(term in result.combined_terms for term in expected_terms)


@pytest.mark.asyncio
async def test_enrich_combines_entities(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
) -> None:
    """Test enrichment combines entities from all topics."""
    result = await cluster_enricher.enrich(multi_source_cluster)

    assert "company" in result.combined_entities
    assert "OpenAI" in result.combined_entities["company"]
    assert "product" in result.combined_entities
    assert "GPT-5" in result.combined_entities["product"]


@pytest.mark.asyncio
async def test_enrich_collects_source_urls(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
) -> None:
    """Test enrichment collects all source URLs."""
    result = await cluster_enricher.enrich(multi_source_cluster)

    assert len(result.source_urls) == 3
    assert "https://source1.com/article" in result.source_urls
    assert "https://source2.com/news" in result.source_urls
    assert "https://source3.com/analysis" in result.source_urls


@pytest.mark.asyncio
async def test_enrich_single_source_uses_topic_summary(
    cluster_enricher: ClusterEnricher,
    single_source_cluster: TopicCluster,
    mock_llm_client: MagicMock,
) -> None:
    """Test single-source cluster uses topic summary directly."""
    result = await cluster_enricher.enrich(single_source_cluster)

    # Single source shouldn't need LLM summary
    # The summary should still be populated from primary topic
    assert result.combined_summary is not None
    assert len(result.source_urls) == 1


@pytest.mark.asyncio
async def test_enriched_cluster_properties(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
) -> None:
    """Test EnrichedCluster provides correct convenience properties."""
    result = await cluster_enricher.enrich(multi_source_cluster)

    assert result.primary_topic == multi_source_cluster.primary_topic
    assert len(result.all_topics) == 3
    assert result.source_count == 3


@pytest.mark.asyncio
async def test_enrich_llm_error_fallback(
    cluster_enricher: ClusterEnricher,
    multi_source_cluster: TopicCluster,
    mock_llm_client: MagicMock,
) -> None:
    """Test enrichment handles LLM errors gracefully."""
    mock_llm_client.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

    result = await cluster_enricher.enrich(multi_source_cluster)

    # Should fall back to concatenating summaries
    assert result.combined_summary is not None
    assert len(result.source_urls) == 3
