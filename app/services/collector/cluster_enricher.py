"""Cluster content enrichment service.

Aggregates and enriches content from all topics in a cluster
using LLM-based summarization.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.infrastructure.llm import LLMClient, LLMConfig
from app.prompts.manager import PromptManager, PromptType
from app.services.collector.clusterer import TopicCluster

if TYPE_CHECKING:
    from app.services.collector.base import ScoredTopic

logger = get_logger(__name__)


@dataclass
class EnrichedCluster:
    """Enriched cluster with aggregated content.

    Attributes:
        cluster: Original topic cluster
        combined_summary: LLM-generated unified summary of all sources
        combined_terms: Merged and deduplicated terms
        combined_entities: Merged entities by type
        source_urls: All source URLs in the cluster
    """

    cluster: TopicCluster
    combined_summary: str
    combined_terms: list[str] = field(default_factory=list)
    combined_entities: dict[str, list[str]] = field(default_factory=dict)
    source_urls: list[str] = field(default_factory=list)

    @property
    def primary_topic(self) -> "ScoredTopic":
        """Get the primary topic from the cluster."""
        return self.cluster.primary_topic

    @property
    def all_topics(self) -> list["ScoredTopic"]:
        """Get all topics from the cluster."""
        return self.cluster.all_topics

    @property
    def source_count(self) -> int:
        """Get number of unique sources."""
        return self.cluster.source_count


class ClusterEnricher:
    """Enriches topic clusters by aggregating and summarizing content.

    Uses LLM to create a unified summary from multiple source topics.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
    ) -> None:
        """Initialize cluster enricher.

        Args:
            llm_client: LLM client for summarization
            prompt_manager: Prompt manager for loading templates
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager

    async def enrich(self, cluster: TopicCluster) -> EnrichedCluster:
        """Enrich a topic cluster with aggregated content.

        Args:
            cluster: Topic cluster to enrich

        Returns:
            EnrichedCluster with unified summary and merged data
        """
        # Merge terms (deduplicated, preserving order)
        combined_terms = self._merge_terms(cluster)

        # Merge entities
        combined_entities = self._merge_entities(cluster)

        # Get all source URLs
        source_urls = cluster.get_all_urls()

        # Generate unified summary using LLM
        combined_summary = await self._generate_summary(cluster)

        logger.info(
            "Cluster enriched",
            primary_title=cluster.primary_topic.title_normalized,
            topic_count=cluster.topic_count,
            source_count=cluster.source_count,
            term_count=len(combined_terms),
        )

        return EnrichedCluster(
            cluster=cluster,
            combined_summary=combined_summary,
            combined_terms=combined_terms,
            combined_entities=combined_entities,
            source_urls=source_urls,
        )

    def _merge_terms(self, cluster: TopicCluster) -> list[str]:
        """Merge terms from all topics in the cluster.

        Args:
            cluster: Topic cluster

        Returns:
            Deduplicated list of terms
        """
        seen = set()
        merged = []

        for topic in cluster.all_topics:
            for term in topic.terms:
                term_lower = term.lower()
                if term_lower not in seen:
                    seen.add(term_lower)
                    merged.append(term)

        return merged

    def _merge_entities(self, cluster: TopicCluster) -> dict[str, list[str]]:
        """Merge entities from all topics in the cluster.

        Args:
            cluster: Topic cluster

        Returns:
            Dictionary of entity type -> list of entities
        """
        merged: dict[str, set[str]] = {}

        for topic in cluster.all_topics:
            entities = topic.entities or {}
            for entity_type, entity_list in entities.items():
                if entity_type not in merged:
                    merged[entity_type] = set()
                merged[entity_type].update(entity_list)

        return {k: list(v) for k, v in merged.items()}

    async def _generate_summary(self, cluster: TopicCluster) -> str:
        """Generate unified summary from all topics using LLM.

        Args:
            cluster: Topic cluster

        Returns:
            Unified summary text
        """
        # Build topics text for the template
        topics_text = self._build_topics_text(cluster)

        try:
            # Load prompt template and settings
            prompt = self.prompt_manager.render(
                PromptType.CLUSTER_SUMMARY,
                topics_text=topics_text,
            )
            llm_settings = self.prompt_manager.get_llm_settings(PromptType.CLUSTER_SUMMARY)

            config = LLMConfig(
                model=llm_settings.model,
                max_tokens=llm_settings.max_tokens,
                temperature=llm_settings.temperature,
            )

            response = await self.llm_client.complete(
                config=config,
                messages=[{"role": "user", "content": prompt}],
            )

            return response.content.strip()

        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            # Fallback: concatenate summaries
            return self._fallback_summary(cluster)

    def _build_topics_text(self, cluster: TopicCluster) -> str:
        """Build topics text for prompt template.

        Args:
            cluster: Topic cluster

        Returns:
            Formatted topics text
        """
        topics_info = []

        for i, topic in enumerate(cluster.all_topics, 1):
            source = topic.metadata.get("source_name", "unknown")
            topics_info.append(
                f"Source {i} ({source}):\n"
                f"Title: {topic.title_original}\n"
                f"Summary: {topic.summary or 'N/A'}"
            )

        return "\n\n".join(topics_info)

    def _fallback_summary(self, cluster: TopicCluster) -> str:
        """Create fallback summary by concatenating topic summaries.

        Args:
            cluster: Topic cluster

        Returns:
            Concatenated summary
        """
        summaries = []
        for topic in cluster.all_topics:
            if topic.summary:
                source = topic.metadata.get("source_name", "unknown")
                summaries.append(f"[{source}] {topic.summary}")

        if summaries:
            return " ".join(summaries[:3])  # Limit to 3 summaries

        return cluster.primary_topic.title_normalized


__all__ = [
    "EnrichedCluster",
    "ClusterEnricher",
]
