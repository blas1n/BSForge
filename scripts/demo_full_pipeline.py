#!/usr/bin/env python
"""Full pipeline demo: Topic Collection → Script → Video Generation.

This script runs the SAME code paths as the production Celery workers,
just invoked synchronously for demo/testing purposes.

Pipeline:
1. TopicCollectionPipeline - Collect, normalize, filter, score topics
2. ScriptGenerator - Generate scene-based script using RAG
3. VideoGenerationPipeline - Generate video from script

All services are obtained from the DI Container, ensuring identical
behavior to production.

Run with: uv run python scripts/demo_full_pipeline.py
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config_loader import ConfigService
from app.core.container import get_container
from app.models.channel import Channel, Persona, TTSService
from app.models.script import Script
from app.models.topic import Topic
from app.services.collector.pipeline import CollectionConfig, TopicCollectionPipeline
from app.services.generator.pipeline import VideoGenerationResult

# ============================================
# CONFIGURABLE VARIABLES
# ============================================

CHANNEL_NAME = "entertainments-kr"  # Channel config name (without .yaml)
VIDEO_TEMPLATE_NAME = "korean_shorts_standard"
OUTPUT_DIR = Path("/tmp/bsforge_full_demo")

# ============================================


async def run_topic_collection(channel: Channel) -> list[Topic]:
    """Run topic collection pipeline.

    Uses TopicCollectionPipeline - same as Celery worker.

    Args:
        channel: Channel model

    Returns:
        List of collected Topic models
    """
    print("\n" + "=" * 60)
    print("PHASE 1: Topic Collection (TopicCollectionPipeline)")
    print("=" * 60)

    container = get_container()

    # Get channel config
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)
    # Convert to dict for CollectionConfig
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
    print(f"   Target language: {config.target_language}")

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
    print(f"   - Global topics: {stats.global_topics}")
    print(f"   - Scoped topics: {stats.scoped_topics}")
    print(f"   - Total collected: {stats.total_collected}")
    print(f"   - Normalized: {stats.normalized_count}")
    print(f"   - Filtered: {stats.filtered_count}")
    print(f"   - Deduplicated: {stats.deduplicated_count}")
    print(f"   - Saved to DB: {stats.saved_count}")

    if stats.errors:
        print(f"   - Errors: {len(stats.errors)}")
        for err in stats.errors[:3]:
            print(f"     • {err[:80]}...")

    if topics:
        print("\n   Top topics:")
        for i, topic in enumerate(topics[:5], 1):
            print(f"   {i}. [{topic.score_total}] {topic.title_normalized[:50]}...")

    return topics


async def run_script_generation(topic: Topic, channel: Channel) -> Script:
    """Run script generation using RAG.

    Uses ScriptGenerator - same as Celery worker.

    Args:
        topic: Topic model
        channel: Channel model

    Returns:
        Generated Script model
    """
    print("\n" + "=" * 60)
    print("PHASE 2: Script Generation (ScriptGenerator)")
    print("=" * 60)

    container = get_container()

    print(f"\n   Topic: {topic.title_normalized}")
    print(f"   Terms: {topic.terms[:5]}")

    # Get ScriptGenerator from container
    script_generator = container.services.script_generator()

    # Generate scene-based script
    script = await script_generator.generate_scene_script(
        topic_id=topic.id,
        channel_id=channel.id,
    )

    print("\n   Script generated:")
    print(f"   - ID: {script.id}")
    print(f"   - Status: {script.status}")
    print(f"   - Has scenes: {script.has_scenes}")

    if script.has_scenes:
        scene_script = script.get_scene_script()
        if scene_script:
            print(f"   - Scene count: {len(scene_script.scenes)}")
            print(f"   - Headline: {scene_script.headline_keyword} / {scene_script.headline_hook}")
            print(f"   - Has commentary: {scene_script.has_commentary}")

            print("\n   Scenes:")
            for i, scene in enumerate(scene_script.scenes[:5], 1):
                print(f"   {i}. [{scene.scene_type.value}] {scene.text[:40]}...")
            if len(scene_script.scenes) > 5:
                print(f"   ... and {len(scene_script.scenes) - 5} more")

    return script


async def run_video_generation(
    script: Script,
    channel: Channel,
) -> VideoGenerationResult:
    """Run video generation pipeline.

    Uses VideoGenerationPipeline - same as Celery worker.

    Args:
        script: Script model
        channel: Channel model

    Returns:
        VideoGenerationResult with paths and metadata
    """
    print("\n" + "=" * 60)
    print("PHASE 3: Video Generation (VideoGenerationPipeline)")
    print("=" * 60)

    container = get_container()

    print(f"\n   Script ID: {script.id}")
    print(f"   Template: {VIDEO_TEMPLATE_NAME}")

    # Get VideoGenerationPipeline from container
    video_pipeline = container.services.video_pipeline()

    # Get persona style from channel config
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)
    persona_style = None
    if channel_config_obj.persona and channel_config_obj.persona.visual_style:
        persona_style = channel_config_obj.persona.visual_style

    # Generate video using scene-based method if available
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
    print(f"   - Thumbnail: {result.thumbnail_path}")

    return result


async def main() -> None:
    """Run full pipeline demo."""
    print("=" * 60)
    print("BSForge Full Pipeline Demo")
    print("Using PRODUCTION service pipelines")
    print("=" * 60)

    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        print("\nERROR: FFmpeg is required for video generation.")
        print("Please install FFmpeg or use DevContainer.")
        return

    # Initialize container
    container = get_container()

    # Load channel config and create Channel model
    print("\n[0/3] Loading channel configuration...")
    config_service = ConfigService()
    channel_config_obj = config_service.get(CHANNEL_NAME)

    channel_info = channel_config_obj.channel
    persona_config = channel_config_obj.persona

    print(f"   Channel: {channel_info.name}")
    print(f"   Persona: {persona_config.name if persona_config else 'Unknown'}")

    # Create or get Channel from DB
    async with container.infrastructure.db_session() as session:
        # Check if channel exists
        result = await session.execute(select(Channel).where(Channel.name == channel_info.name))
        channel = result.scalar_one_or_none()

        if not channel:
            # Create new channel with persona
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
            await session.flush()  # Get channel.id before creating persona

            # Create persona from config
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
            print(f"   Created new channel in DB: {channel.id}")
            print(f"   Created persona: {persona.name}")
        else:
            print(f"   Using existing channel from DB: {channel.id}")

    # Phase 1: Topic Collection
    topics = await run_topic_collection(channel)

    if not topics:
        print("\nNo topics collected. Demo ended.")
        return

    # Select best topic
    best_topic = topics[0]
    print(f"\n   Selected topic: {best_topic.title_normalized}")

    # Phase 2: Script Generation
    script = await run_script_generation(best_topic, channel)

    if not script:
        print("\nFailed to generate script. Demo ended.")
        return

    # Phase 3: Video Generation
    result = await run_video_generation(script, channel)

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(f"\nFinal video: {result.video_path}")
    print(f"Thumbnail: {result.thumbnail_path}")
    print(f"Duration: {result.duration_seconds:.1f}s")

    print("\nTo view the video:")
    print(f"  1. Copy from container: docker cp <container>:{result.video_path} ./output.mp4")
    print("  2. Or open in VSCode file explorer")


if __name__ == "__main__":
    asyncio.run(main())
