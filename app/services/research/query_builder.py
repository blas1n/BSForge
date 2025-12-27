"""Research query builder.

Builds search queries from topic clusters using configurable strategies.
"""

from __future__ import annotations

import logging

from app.config.research import QueryStrategy, ResearchConfig
from app.infrastructure.llm import LLMClient, LLMConfig
from app.prompts.manager import PromptManager, PromptType
from app.services.collector.clusterer import TopicCluster

logger = logging.getLogger(__name__)


class ResearchQueryBuilder:
    """Builds search queries from topic clusters.

    Supports multiple strategies for query generation based on channel config.

    Attributes:
        llm_client: Optional LLM client for LLM strategy
        prompt_manager: Prompt manager for loading templates
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
    ) -> None:
        """Initialize query builder.

        Args:
            llm_client: LLM client for LLM-based query generation
            prompt_manager: Prompt manager for loading templates
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager

    async def build_queries(
        self,
        cluster: TopicCluster,
        config: ResearchConfig,
    ) -> list[str]:
        """Build search queries from a topic cluster.

        Args:
            cluster: Topic cluster to build queries for
            config: Research configuration with strategy

        Returns:
            List of search queries
        """
        match config.query_strategy:
            case QueryStrategy.KEYWORD:
                return self._build_from_keywords(cluster, config.max_queries)
            case QueryStrategy.TITLE:
                return self._build_from_title(cluster, config.max_queries)
            case QueryStrategy.LLM:
                return await self._build_with_llm(cluster, config.max_queries)

    def _build_from_keywords(
        self,
        cluster: TopicCluster,
        max_queries: int,
    ) -> list[str]:
        """Build queries from combined_terms keywords.

        Creates queries by combining top keywords.

        Args:
            cluster: Topic cluster
            max_queries: Maximum number of queries

        Returns:
            List of keyword-based queries
        """
        terms = cluster.combined_terms[:10]  # Top 10 terms

        if not terms:
            # Fallback to title
            return [cluster.primary_topic.title_normalized]

        queries = []

        # Primary query: top 3-4 terms
        primary_terms = terms[:4]
        queries.append(" ".join(primary_terms))

        # Additional queries: different term combinations
        if len(terms) >= 5 and max_queries >= 2:
            queries.append(" ".join(terms[2:6]))

        if len(terms) >= 7 and max_queries >= 3:
            queries.append(" ".join(terms[4:8]))

        return queries[:max_queries]

    def _build_from_title(
        self,
        cluster: TopicCluster,
        max_queries: int,
    ) -> list[str]:
        """Build queries from topic titles.

        Uses the primary topic title directly.

        Args:
            cluster: Topic cluster
            max_queries: Maximum number of queries

        Returns:
            List of title-based queries
        """
        queries = [cluster.primary_topic.title_normalized]

        # Add related topic titles if available
        for related in cluster.related_topics[: max_queries - 1]:
            if related.title_normalized != cluster.primary_topic.title_normalized:
                queries.append(related.title_normalized)

        return queries[:max_queries]

    async def _build_with_llm(
        self,
        cluster: TopicCluster,
        max_queries: int,
    ) -> list[str]:
        """Build queries using LLM.

        Generates optimal search queries based on topic context.

        Args:
            cluster: Topic cluster
            max_queries: Maximum number of queries

        Returns:
            List of LLM-generated queries
        """
        try:
            # Build template variables
            titles = cluster.get_all_titles()[:5]
            terms = cluster.combined_terms[:10]
            related_titles = (
                "\n".join(f"- {t}" for t in titles[1:]) if len(titles) > 1 else "- None"
            )

            # Render prompt from template
            prompt = self.prompt_manager.render(
                PromptType.RESEARCH_QUERY,
                max_queries=max_queries,
                topic_title=cluster.primary_topic.title_normalized,
                related_titles=related_titles,
                keywords=", ".join(terms),
            )
            llm_settings = self.prompt_manager.get_llm_settings(PromptType.RESEARCH_QUERY)

            config = LLMConfig(
                model=llm_settings.model,
                max_tokens=llm_settings.max_tokens,
                temperature=llm_settings.temperature,
            )

            response = await self.llm_client.complete(
                config=config,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response - expect one query per line
            queries = [
                line.strip().lstrip("- ").lstrip("• ")
                for line in response.content.strip().split("\n")
                if line.strip() and not line.startswith("#")
            ]

            return queries[:max_queries]

        except Exception as e:
            logger.error(f"LLM query generation failed: {e}")
            return self._build_from_keywords(cluster, max_queries)


__all__ = ["ResearchQueryBuilder"]
