#!/usr/bin/env python
"""BSForge Full Pipeline Demo: Topic → Script → Video.

This script demonstrates the complete video generation pipeline:
1. Topic Collection: Collect from multiple sources (RSS, communities, etc.)
2. Clustering: Group similar topics for multi-source integration
3. Enrichment: LLM-based summarization + Web research (Tavily)
4. Script Generation: Scene-based script with persona context
5. Video Generation: TTS + visuals + subtitles → MP4

Features:
- Multi-source topic clustering
- Web research integration (Tavily API)
- YAML-based prompt templates
- Scene-based video generation
- AI-generated visuals (Stable Diffusion)

Run with: uv run python scripts/demo_pipeline.py
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.config.enrichment import EnrichmentConfig
from app.config.research import QueryStrategy, ResearchConfig
from app.core.config import get_config
from app.core.config_loader import ConfigService
from app.core.container import get_container
from app.models.channel import Channel, Persona, TTSService
from app.models.script import Script
from app.models.topic import Topic
from app.services.collector.clusterer import TopicCluster, cluster_topics
from app.services.collector.pipeline import CollectionConfig, TopicCollectionPipeline
from app.services.generator.pipeline import VideoGenerationResult
from app.services.pipeline.enriched_generation import EnrichedGenerationPipeline

# ============================================
# CONFIGURABLE VARIABLES
# ============================================

CHANNEL_NAME = "entertainments-kr"  # Channel config name (without .yaml)
VIDEO_TEMPLATE_NAME = "korean_shorts_standard"
OUTPUT_DIR = Path("/tmp/bsforge_demo")

# Enrichment settings
ENABLE_WEB_RESEARCH = True  # Set False if no Tavily API key
QUERY_STRATEGY = QueryStrategy.KEYWORD  # KEYWORD, TITLE, or LLM
MIN_CLUSTER_SIZE = 1  # Minimum topics for LLM summary (1 = always summarize)

# ============================================


async def run_topic_collection(channel: Channel) -> tuple[list[Topic], list[TopicCluster]]:
    """Run topic collection and clustering.

    Args:
        channel: Channel model

    Returns:
        Tuple of (topics, clusters)
    """
    print("\n" + "=" * 60)
    print("PHASE 1: Topic Collection & Clustering")
    print("=" * 60)

    container = get_container()

    # Get channel config
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)
    channel_config_dict = {
        "topic_collection": {
            "global_sources": channel_config_obj.topic_collection.global_sources,
            "scoped_sources": channel_config_obj.topic_collection.scoped_sources,
            "target_language": channel_config_obj.topic_collection.target_language,
            "source_overrides": channel_config_obj.topic_collection.source_overrides,
        },
        "filtering": {
            "include": channel_config_obj.filtering.include if channel_config_obj.filtering else [],
            "exclude": channel_config_obj.filtering.exclude if channel_config_obj.filtering else [],
        },
    }
    config = CollectionConfig.from_channel_config(channel_config_dict)

    print(f"\n   Channel: {channel.name}")
    print(f"   Global sources: {config.global_sources}")
    print(f"   Scoped sources: {config.scoped_sources}")

    # Get pipeline dependencies from container
    async with container.infrastructure.db_session() as session:
        pipeline = TopicCollectionPipeline(
            session=session,
            http_client=container.infrastructure.http_client(),
            normalizer=container.services.topic_normalizer(),
            redis=container.redis(),
            deduplicator=container.services.topic_deduplicator(),
            scorer=container.services.topic_scorer(),
            global_pool=container.services.global_topic_pool(),
            scoped_cache=container.services.scoped_source_cache(),
        )

        topics, stats = await pipeline.collect_for_channel(channel, config)

    print("\n   Collection Stats:")
    print(f"   - Total collected: {stats.total_collected}")
    print(f"   - Saved to DB: {stats.saved_count}")

    if not topics:
        return [], []

    # Cluster topics
    print("\n   Clustering topics...")

    # Convert Topic models to ScoredTopic DTOs for clustering
    from app.services.collector.base import ScoredTopic

    scored_topics = []
    for topic in topics:
        # Use topic.id as fallback for source_id
        source_id = topic.source_id if topic.source_id else str(topic.id)
        scored = ScoredTopic(
            source_id=source_id,
            source_url=topic.source_url,
            title_original=topic.title_original,
            title_normalized=topic.title_normalized,
            title_translated=topic.title_translated,
            summary=topic.summary or "",
            terms=topic.terms or [],
            entities=topic.entities or {},
            language=topic.language,
            content_hash=topic.content_hash,
            metrics={},  # Topic model doesn't have metrics
            metadata={"source_name": "collected", "topic_id": str(topic.id)},
            published_at=topic.published_at,
            score_source=topic.score_source or 0.0,
            score_freshness=topic.score_freshness or 0.0,
            score_trend=topic.score_trend or 0.0,
            score_relevance=topic.score_relevance or 0.0,
            score_total=topic.score_total or 0,
        )
        scored_topics.append(scored)

    clusters = cluster_topics(
        scored_topics,
        similarity_threshold=0.3,
        total_sources=len(config.global_sources) + len(config.scoped_sources),
    )

    print(f"   - Topics: {len(topics)}")
    print(f"   - Clusters: {len(clusters)}")

    if clusters:
        print("\n   Top clusters:")
        for i, cluster in enumerate(clusters[:3], 1):
            print(f"   {i}. [{cluster.topic_count} topics, {cluster.source_count} sources]")
            print(f"      {cluster.primary_topic.title_normalized[:50]}...")

    return topics, clusters


async def run_enriched_script_generation(
    cluster: TopicCluster,
    primary_topic: Topic,
    channel: Channel,
) -> Script:
    """Run enriched script generation.

    Args:
        cluster: Topic cluster
        primary_topic: Primary topic (DB model)
        channel: Channel model

    Returns:
        Generated Script
    """
    print("\n" + "=" * 60)
    print("PHASE 2: Enriched Script Generation")
    print("=" * 60)

    container = get_container()
    config = get_config()

    print(f"\n   Cluster: {cluster.primary_topic.title_normalized[:50]}...")
    print(f"   Topics in cluster: {cluster.topic_count}")
    print(f"   Sources: {cluster.sources}")
    print(f"   Combined terms: {cluster.combined_terms[:5]}")

    # Check Tavily API key
    has_tavily = bool(config.tavily_api_key)
    enable_research = ENABLE_WEB_RESEARCH and has_tavily

    if not has_tavily:
        print("\n   WARNING: TAVILY_API_KEY not set. Web research disabled.")

    # Configure enrichment
    enrichment_config = EnrichmentConfig(
        cluster={"enabled": True, "min_cluster_size": MIN_CLUSTER_SIZE},
        research=ResearchConfig(
            enabled=enable_research,
            query_strategy=QUERY_STRATEGY,
            max_queries=3,
            max_results_per_query=3,
        ),
    )

    print("\n   Enrichment config:")
    print("   - Cluster enrichment: enabled")
    print(f"   - Web research: {'enabled' if enable_research else 'disabled'}")
    print(f"   - Query strategy: {QUERY_STRATEGY.value}")

    # Get enriched pipeline from container
    enriched_pipeline: EnrichedGenerationPipeline = container.services.enriched_pipeline()

    # Generate script
    print("\n   Generating enriched script...")
    script = await enriched_pipeline.generate_from_cluster(
        cluster=cluster,
        channel_id=channel.id,
        primary_topic_id=primary_topic.id,
        config=enrichment_config,
    )

    print("\n   Script generated:")
    print(f"   - ID: {script.id}")
    print(f"   - Status: {script.status}")
    print(f"   - Quality passed: {script.quality_passed}")

    if script.generation_metadata:
        meta = script.generation_metadata
        print(f"   - Enriched: {meta.get('enriched', False)}")
        print(f"   - Cluster sources: {meta.get('cluster_source_count', 0)}")
        print(f"   - Research results: {meta.get('research_result_count', 0)}")

    if script.has_scenes:
        scene_script = script.get_scene_script()
        if scene_script:
            print(f"   - Scene count: {len(scene_script.scenes)}")
            print(f"   - Headline: {scene_script.headline_keyword}")

            print("\n   Scenes:")
            for i, scene in enumerate(scene_script.scenes[:5], 1):
                print(f"   {i}. [{scene.scene_type.value}] {scene.text[:40]}...")

    return script


async def run_video_generation(
    script: Script,
) -> VideoGenerationResult:
    """Run video generation pipeline.

    Args:
        script: Script model

    Returns:
        VideoGenerationResult
    """
    print("\n" + "=" * 60)
    print("PHASE 3: Video Generation")
    print("=" * 60)

    container = get_container()

    print(f"\n   Script ID: {script.id}")
    print(f"   Template: {VIDEO_TEMPLATE_NAME}")

    # Get VideoGenerationPipeline from container
    video_pipeline = container.services.video_pipeline()

    # Get persona style
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)
    persona_style = None
    if channel_config_obj.persona and channel_config_obj.persona.visual_style:
        persona_style = channel_config_obj.persona.visual_style

    # Generate video
    if script.has_scenes:
        scene_script = script.get_scene_script()
        if scene_script:
            result = await video_pipeline.generate_from_scenes(
                script=script,
                scene_script=scene_script,
                template_name=VIDEO_TEMPLATE_NAME,
                persona_style=persona_style,
            )
        else:
            result = await video_pipeline.generate(
                script=script,
                template_name=VIDEO_TEMPLATE_NAME,
            )
    else:
        result = await video_pipeline.generate(
            script=script,
            template_name=VIDEO_TEMPLATE_NAME,
        )

    print("\n   Video generated:")
    print(f"   - Path: {result.video_path}")
    print(f"   - Duration: {result.duration_seconds:.1f}s")
    print(f"   - Size: {result.file_size_bytes / 1024 / 1024:.2f} MB")
    print(f"   - TTS: {result.tts_service} / {result.tts_voice_id}")
    print(f"   - Visual sources: {result.visual_sources}")
    print(f"   - Generation time: {result.generation_time_seconds}s")

    return result


async def main() -> None:
    """Run enriched pipeline demo."""
    print("=" * 60)
    print("BSForge Full Pipeline Demo")
    print("Topic → Script → Video Generation")
    print("=" * 60)

    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        print("\nERROR: FFmpeg is required for video generation.")
        return

    # Import get_config for Tavily check

    container = get_container()
    config = get_config()

    # Load channel config
    print("\n[0/3] Loading channel configuration...")
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)

    channel_info = channel_config_obj.channel
    persona_config = channel_config_obj.persona

    print(f"   Channel: {channel_info.name}")
    print(f"   Persona: {persona_config.name if persona_config else 'Unknown'}")
    print(f"   Tavily API: {'configured' if config.tavily_api_key else 'NOT configured'}")

    # Create or get Channel from DB
    async with container.infrastructure.db_session() as session:
        result = await session.execute(select(Channel).where(Channel.name == channel_info.name))
        channel = result.scalar_one_or_none()

        if not channel:
            channel = Channel(
                id=uuid.uuid4(),
                name=channel_info.name,
                description=channel_info.description,
                youtube_channel_id=(
                    channel_info.youtube.channel_id if channel_info.youtube.channel_id else None
                ),
                youtube_handle=channel_info.youtube.handle if channel_info.youtube else None,
                topic_config=(
                    channel_config_obj.topic_collection.model_dump()
                    if channel_config_obj.topic_collection
                    else {}
                ),
                content_config=(
                    channel_config_obj.content.model_dump() if channel_config_obj.content else {}
                ),
            )
            session.add(channel)
            await session.flush()

            voice_config = persona_config.voice if persona_config else None
            persona = Persona(
                channel_id=channel.id,
                name=persona_config.name if persona_config else channel_info.name,
                tagline=persona_config.tagline if persona_config else None,
                voice_gender=voice_config.gender if voice_config else None,
                tts_service=(
                    TTSService(voice_config.service)
                    if voice_config and voice_config.service
                    else TTSService.EDGE_TTS
                ),
                voice_id=voice_config.voice_id if voice_config else None,
                voice_settings=(
                    voice_config.settings.model_dump()
                    if voice_config and voice_config.settings
                    else None
                ),
                communication_style=(
                    persona_config.communication.model_dump()
                    if persona_config and persona_config.communication
                    else None
                ),
                perspective=(
                    persona_config.perspective.model_dump()
                    if persona_config and persona_config.perspective
                    else None
                ),
            )
            session.add(persona)
            await session.commit()
            await session.refresh(channel)
            print(f"   Created channel: {channel.id}")
        else:
            print(f"   Using existing channel: {channel.id}")

    # Phase 1: Topic Collection & Clustering
    topics, clusters = await run_topic_collection(channel)

    if not topics or not clusters:
        # Try to get existing topics from DB
        print("\n   No new topics. Fetching existing topics from DB...")
        async with container.infrastructure.db_session() as session:
            from app.models.topic import Topic as TopicModel

            result = await session.execute(
                select(TopicModel)
                .where(TopicModel.channel_id == channel.id)
                .order_by(TopicModel.score_total.desc())
                .limit(10)
            )
            db_topics = list(result.scalars().all())

            if not db_topics:
                print("\nNo topics available. Demo ended.")
                return

            print(f"   Found {len(db_topics)} existing topics in DB")

            # Convert to ScoredTopic for clustering
            from app.services.collector.base import ScoredTopic

            scored_topics = []
            for topic in db_topics:
                # Use topic.id as fallback for source_id (required field)
                source_id = topic.source_id if topic.source_id else str(topic.id)
                scored = ScoredTopic(
                    source_id=source_id,
                    source_url=topic.source_url,
                    title_original=topic.title_original,
                    title_normalized=topic.title_normalized,
                    title_translated=topic.title_translated,
                    summary=topic.summary or "",
                    terms=topic.terms or [],
                    entities=topic.entities or {},
                    language=topic.language,
                    content_hash=topic.content_hash,
                    metrics={},
                    metadata={"source_name": "db", "topic_id": str(topic.id)},
                    published_at=topic.published_at,
                    score_source=topic.score_source or 0.0,
                    score_freshness=topic.score_freshness or 0.0,
                    score_trend=topic.score_trend or 0.0,
                    score_relevance=topic.score_relevance or 0.0,
                    score_total=topic.score_total or 0,
                )
                scored_topics.append(scored)

            if not scored_topics:
                print("\nNo valid topics available. Demo ended.")
                return

            clusters = cluster_topics(scored_topics, similarity_threshold=0.3)
            topics = db_topics

            print(f"   Clustered into {len(clusters)} clusters")

    # Select best cluster
    best_cluster = clusters[0]
    print(f"\n   Selected cluster: {best_cluster.primary_topic.title_normalized[:50]}...")

    # Find the primary topic in DB
    primary_topic_id = best_cluster.primary_topic.metadata.get("topic_id")
    if not primary_topic_id:
        # Fallback: use first topic
        primary_topic = topics[0]
    else:
        # Find matching topic
        primary_topic = next(
            (t for t in topics if str(t.id) == primary_topic_id),
            topics[0],
        )

    # Phase 2: Enriched Script Generation
    script = await run_enriched_script_generation(best_cluster, primary_topic, channel)

    if not script:
        print("\nFailed to generate script. Demo ended.")
        return

    # Phase 3: Video Generation
    result = await run_video_generation(script)

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(f"\nFinal video: {result.video_path}")
    print(f"Duration: {result.duration_seconds:.1f}s")

    if script.generation_metadata:
        meta = script.generation_metadata
        print("\nEnrichment stats:")
        print(f"  - Sources integrated: {meta.get('cluster_source_count', 0)}")
        print(f"  - Research results used: {meta.get('research_result_count', 0)}")

    print("\nTo view the video:")
    print(f"  docker cp <container>:{result.video_path} ./output.mp4")


if __name__ == "__main__":
    asyncio.run(main())
