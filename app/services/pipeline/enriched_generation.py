"""Enriched script generation pipeline.

Orchestrates the complete enriched generation flow:
1. Cluster content integration
2. Web research
3. Context building with enrichment
4. Script generation with enhanced context
"""

from __future__ import annotations

import uuid

from app.config.enrichment import EnrichmentConfig
from app.config.rag import GenerationConfig
from app.config.research import ResearchConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.scene import SceneScript
from app.models.script import Script, ScriptStatus
from app.prompts.manager import PromptType
from app.services.collector.cluster_enricher import ClusterEnricher, EnrichedCluster
from app.services.collector.clusterer import TopicCluster
from app.services.rag.context import ContextBuilder, EnrichedContent, GenerationContext
from app.services.rag.generator import ScriptGenerator
from app.services.research.base import BaseResearchClient, ResearchResult
from app.services.research.query_builder import ResearchQueryBuilder

logger = get_logger(__name__)


class EnrichedGenerationPipeline:
    """Orchestrates enriched script generation from topic clusters.

    Combines:
    - Cluster content enrichment (multi-source integration)
    - Web research (Tavily)
    - Existing RAG + ScriptGenerator

    Attributes:
        cluster_enricher: Cluster content aggregation service
        research_client: Web research client (Tavily)
        query_builder: Research query builder
        context_builder: RAG context builder
        script_generator: Script generation service
        db_session_factory: Database session factory
    """

    def __init__(
        self,
        cluster_enricher: ClusterEnricher,
        research_client: BaseResearchClient,
        query_builder: ResearchQueryBuilder,
        context_builder: ContextBuilder,
        script_generator: ScriptGenerator,
        db_session_factory: SessionFactory,
    ) -> None:
        """Initialize pipeline.

        Args:
            cluster_enricher: Cluster content aggregation service
            research_client: Web research client
            query_builder: Research query builder
            context_builder: RAG context builder
            script_generator: Script generation service
            db_session_factory: Database session factory
        """
        self.cluster_enricher = cluster_enricher
        self.research_client = research_client
        self.query_builder = query_builder
        self.context_builder = context_builder
        self.script_generator = script_generator
        self.db_session_factory = db_session_factory

    async def generate_from_cluster(
        self,
        cluster: TopicCluster,
        channel_id: uuid.UUID,
        primary_topic_id: uuid.UUID,
        config: EnrichmentConfig,
    ) -> Script:
        """Generate script from topic cluster with enrichment.

        Pipeline:
        1. Enrich cluster content (aggregate all topics)
        2. Perform web research
        3. Build enriched context
        4. Generate script

        Args:
            cluster: Topic cluster to generate from
            channel_id: Channel UUID
            primary_topic_id: UUID of the primary topic (stored in DB)
            config: Enrichment configuration

        Returns:
            Generated Script object
        """
        logger.info(
            "Starting enriched generation pipeline",
            extra={
                "cluster_size": cluster.topic_count,
                "source_count": cluster.source_count,
                "primary_topic": cluster.primary_topic.title_normalized,
            },
        )

        # Step 1: Enrich cluster content
        enriched_cluster = await self._enrich_cluster(cluster, config)

        # Step 2: Perform web research
        research_results = await self._perform_research(
            enriched_cluster,
            config.research,
        )

        # Step 3: Build enriched content
        enriched_content = EnrichedContent(
            cluster_summary=enriched_cluster.combined_summary,
            cluster_sources=enriched_cluster.source_urls,
            research_results=research_results,
        )

        # Step 4: Build context with enrichment
        context = await self._build_enriched_context(
            topic_id=primary_topic_id,
            enriched_content=enriched_content,
            channel_id=channel_id,
            generation_config=config.generation,
        )

        # Step 5: Generate script using existing generator
        script = await self._generate_script(context, config.generation)

        logger.info(
            "Enriched generation complete",
            extra={
                "script_id": str(script.id),
                "sources_used": len(enriched_cluster.source_urls),
                "research_results": len(research_results),
            },
        )

        return script

    async def _enrich_cluster(
        self,
        cluster: TopicCluster,
        config: EnrichmentConfig,
    ) -> EnrichedCluster:
        """Enrich cluster content.

        Args:
            cluster: Topic cluster
            config: Enrichment configuration

        Returns:
            EnrichedCluster with aggregated content
        """
        if not config.cluster.enabled:
            logger.info("Cluster enrichment disabled, using minimal enrichment")
            return EnrichedCluster(
                cluster=cluster,
                combined_summary=cluster.primary_topic.summary or "",
                combined_terms=cluster.combined_terms,
                source_urls=cluster.get_all_urls(),
            )

        if cluster.topic_count < config.cluster.min_cluster_size:
            logger.info(
                f"Cluster size {cluster.topic_count} < min {config.cluster.min_cluster_size}, "
                "skipping LLM summary"
            )
            return EnrichedCluster(
                cluster=cluster,
                combined_summary=cluster.primary_topic.summary or "",
                combined_terms=cluster.combined_terms,
                source_urls=cluster.get_all_urls(),
            )

        return await self.cluster_enricher.enrich(cluster)

    async def _perform_research(
        self,
        enriched_cluster: EnrichedCluster,
        config: ResearchConfig,
    ) -> list[ResearchResult]:
        """Perform web research for the cluster.

        Args:
            enriched_cluster: Enriched cluster
            config: Research configuration

        Returns:
            List of research results
        """
        if not config.enabled:
            logger.info("Web research disabled")
            return []

        # Build search queries using configured strategy
        queries = await self.query_builder.build_queries(
            cluster=enriched_cluster.cluster,
            config=config,
        )

        if not queries:
            logger.warning("No search queries generated")
            return []

        logger.info(f"Performing web research with {len(queries)} queries")

        # Execute search
        responses = await self.research_client.search_batch(
            queries=queries,
            max_results_per_query=config.max_results_per_query,
        )

        # Collect all results
        all_results: list[ResearchResult] = []
        seen_urls: set[str] = set()

        for response in responses:
            for result in response.results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    all_results.append(result)

        # Sort by score and limit
        all_results.sort(key=lambda r: r.score, reverse=True)
        max_results = config.max_results_per_query * config.max_queries
        all_results = all_results[:max_results]

        logger.info(f"Collected {len(all_results)} unique research results")

        return all_results

    async def _build_enriched_context(
        self,
        topic_id: uuid.UUID,
        enriched_content: EnrichedContent,
        channel_id: uuid.UUID,
        generation_config: GenerationConfig,
    ) -> GenerationContext:
        """Build generation context with enrichment.

        Args:
            topic_id: Primary topic UUID (stored in DB)
            enriched_content: Enriched content (cluster + research)
            channel_id: Channel UUID
            generation_config: Generation configuration

        Returns:
            GenerationContext with enrichment
        """
        # Use existing context builder
        context = await self.context_builder.build_context(
            topic_id=topic_id,
            channel_id=channel_id,
            config=generation_config,
        )

        # Add enriched content
        context.enriched = enriched_content

        return context

    async def _generate_script(
        self,
        context: GenerationContext,
        config: GenerationConfig,
    ) -> Script:
        """Generate script using the enriched context.

        Args:
            context: Generation context with enrichment
            config: Generation configuration

        Returns:
            Generated Script
        """
        # Inject enriched context into generator's context builder temporarily
        # by calling the internal method directly with the pre-built context

        # Build prompt with enriched context
        prompt = await self.script_generator.prompt_builder.build_prompt(context)

        # Get LLM config
        llm_config = self.script_generator._get_llm_config_from_template(
            PromptType.SCRIPT_GENERATION
        )

        # Generate
        logger.info(f"Generating script with enriched context ({llm_config.model})")

        response = await self.script_generator.llm_client.complete(
            config=llm_config,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_response = response.content.strip()

        # Parse scenes
        scene_script = self.script_generator._parse_scene_response(raw_response)
        scene_script.apply_recommended_transitions()

        # Quality check
        quality_result = await self.script_generator._check_scene_quality(
            scene_script=scene_script,
            persona=context.persona,
        )

        if not quality_result["passed"]:
            logger.warning(f"Quality check failed: {quality_result['reasons']}")
            # Still save but mark as failed
            quality_result["passed"] = False

        # Save script with enrichment metadata
        script = await self._save_enriched_script(
            channel_id=context.topic.channel_id,
            topic_id=context.topic.id,
            scene_script=scene_script,
            quality_result=quality_result,
            config=config,
            model_used=llm_config.model,
            context_chunks_used=len(context.retrieved.similar),
            enriched_content=context.enriched,
        )

        # Chunk and embed
        await self.script_generator._chunk_and_embed(script)

        return script

    async def _save_enriched_script(
        self,
        channel_id: uuid.UUID,
        topic_id: uuid.UUID,
        scene_script: SceneScript,
        quality_result: dict[str, object],
        config: GenerationConfig,
        model_used: str,
        context_chunks_used: int,
        enriched_content: EnrichedContent | None,
    ) -> Script:
        """Save script with enrichment metadata.

        Args:
            channel_id: Channel UUID
            topic_id: Topic UUID
            scene_script: SceneScript object
            quality_result: Quality check results
            config: Generation config
            model_used: LLM model used
            context_chunks_used: Number of RAG chunks used
            enriched_content: Enrichment data

        Returns:
            Saved Script
        """
        full_text = scene_script.full_text
        word_count = len(full_text.split())
        scenes_data = [scene.model_dump(mode="json") for scene in scene_script.scenes]

        # Build enrichment metadata
        enrichment_meta = {}
        if enriched_content:
            enrichment_meta = {
                "cluster_source_count": len(enriched_content.cluster_sources),
                "cluster_sources": enriched_content.cluster_sources[:5],
                "research_result_count": len(enriched_content.research_results),
                "research_sources": [r.source for r in enriched_content.research_results[:5]],
            }

        script = Script(
            channel_id=channel_id,
            topic_id=topic_id,
            script_text=full_text,
            scenes=scenes_data,
            estimated_duration=quality_result["duration"],
            word_count=word_count,
            style_score=quality_result["style_score"],
            hook_score=quality_result["hook_score"],
            forbidden_words=quality_result["forbidden_words"],
            quality_passed=quality_result["passed"],
            generation_model=model_used,
            context_chunks_used=context_chunks_used,
            generation_metadata={
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "target_duration": config.target_duration,
                "style": config.style,
                "format": config.format,
                "scene_based": True,
                "scene_count": quality_result["scene_count"],
                "has_commentary": quality_result["has_commentary"],
                "enriched": True,
                **enrichment_meta,
            },
            status=ScriptStatus.GENERATED,
        )

        async with self.db_session_factory() as session:
            session.add(script)
            await session.commit()
            await session.refresh(script)

        return script


__all__ = ["EnrichedGenerationPipeline"]
