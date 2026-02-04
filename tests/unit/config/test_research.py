"""Unit tests for research configuration models."""

import pytest
from pydantic import ValidationError

from app.config.research import QueryStrategy, ResearchConfig


class TestQueryStrategy:
    """Tests for QueryStrategy enum."""

    def test_enum_values(self):
        """Test enum values exist."""
        assert QueryStrategy.KEYWORD.value == "keyword"
        assert QueryStrategy.TITLE.value == "title"
        assert QueryStrategy.LLM.value == "llm"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert QueryStrategy("keyword") == QueryStrategy.KEYWORD
        assert QueryStrategy("title") == QueryStrategy.TITLE
        assert QueryStrategy("llm") == QueryStrategy.LLM


class TestResearchConfig:
    """Tests for ResearchConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ResearchConfig()
        assert config.enabled is True
        assert config.provider == "tavily"
        assert config.query_strategy == QueryStrategy.KEYWORD
        assert config.search_depth == "basic"
        assert config.topic_type == "general"
        assert config.max_queries == 3
        assert config.max_results_per_query == 5
        assert config.include_answer is True
        assert config.timeout == 30.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ResearchConfig(
            enabled=False,
            query_strategy=QueryStrategy.LLM,
            search_depth="advanced",
            topic_type="news",
            max_queries=5,
            max_results_per_query=10,
            include_answer=False,
            timeout=60.0,
        )
        assert config.enabled is False
        assert config.query_strategy == QueryStrategy.LLM
        assert config.search_depth == "advanced"
        assert config.topic_type == "news"
        assert config.max_queries == 5
        assert config.max_results_per_query == 10
        assert config.include_answer is False
        assert config.timeout == 60.0

    def test_provider_only_tavily(self):
        """Test that only tavily provider is allowed."""
        config = ResearchConfig(provider="tavily")
        assert config.provider == "tavily"

        with pytest.raises(ValidationError):
            ResearchConfig(provider="google")

    def test_search_depth_options(self):
        """Test search_depth validation."""
        config = ResearchConfig(search_depth="basic")
        assert config.search_depth == "basic"

        config = ResearchConfig(search_depth="advanced")
        assert config.search_depth == "advanced"

        with pytest.raises(ValidationError):
            ResearchConfig(search_depth="invalid")

    def test_topic_type_options(self):
        """Test topic_type validation."""
        config = ResearchConfig(topic_type="general")
        assert config.topic_type == "general"

        config = ResearchConfig(topic_type="news")
        assert config.topic_type == "news"

        with pytest.raises(ValidationError):
            ResearchConfig(topic_type="invalid")

    def test_max_queries_range(self):
        """Test max_queries validation."""
        config = ResearchConfig(max_queries=1)
        assert config.max_queries == 1

        config = ResearchConfig(max_queries=10)
        assert config.max_queries == 10

        with pytest.raises(ValidationError):
            ResearchConfig(max_queries=0)

        with pytest.raises(ValidationError):
            ResearchConfig(max_queries=11)

    def test_max_results_per_query_range(self):
        """Test max_results_per_query validation."""
        config = ResearchConfig(max_results_per_query=1)
        assert config.max_results_per_query == 1

        config = ResearchConfig(max_results_per_query=10)
        assert config.max_results_per_query == 10

        with pytest.raises(ValidationError):
            ResearchConfig(max_results_per_query=0)

        with pytest.raises(ValidationError):
            ResearchConfig(max_results_per_query=11)

    def test_timeout_range(self):
        """Test timeout validation."""
        config = ResearchConfig(timeout=5.0)
        assert config.timeout == 5.0

        config = ResearchConfig(timeout=120.0)
        assert config.timeout == 120.0

        with pytest.raises(ValidationError):
            ResearchConfig(timeout=4.9)

        with pytest.raises(ValidationError):
            ResearchConfig(timeout=120.1)

    def test_query_strategy_from_string(self):
        """Test query_strategy accepts string values."""
        config = ResearchConfig(query_strategy="keyword")
        assert config.query_strategy == QueryStrategy.KEYWORD

        config = ResearchConfig(query_strategy="llm")
        assert config.query_strategy == QueryStrategy.LLM
