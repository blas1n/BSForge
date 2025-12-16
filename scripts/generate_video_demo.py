#!/usr/bin/env python3
"""Full Production Pipeline: Channel Config → DB → Topic → Script → Video.

Usage:
    uv run python scripts/generate_video_demo.py [channel_config]

Example:
    uv run python scripts/generate_video_demo.py config/channels/ai_tech.yaml

This script runs the FULL BSForge production pipeline with DB integration:
1. Load channel config → Create/update Channel + Persona in DB
2. Collect topics → TopicCollectionPipeline service
3. Generate script → ScriptGenerator service with RAG
4. Generate video → VideoGenerationPipeline service
5. Save Video record to DB

Prerequisites:
- PostgreSQL running (DevContainer provides this)
- Redis running (DevContainer provides this)
- OPENAI_API_KEY or ANTHROPIC_API_KEY in .env
- Run migrations: alembic upgrade head
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import container
from app.core.logging import get_logger
from app.models.channel import Channel, ChannelStatus, Persona, TTSService
from app.models.script import Script, ScriptStatus
from app.models.topic import Topic, TopicStatus
from app.services.collector.pipeline import CollectionConfig, TopicCollectionPipeline

logger = get_logger(__name__)


def load_channel_config(config_path: Path) -> dict[str, Any]:
    """Load channel configuration from YAML file."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# =============================================================================
# Step 1: Channel & Persona Setup (DB)
# =============================================================================


async def setup_channel_and_persona(
    session: AsyncSession,
    channel_config: dict[str, Any],
) -> tuple[Channel, Persona]:
    """Create or update channel and persona in database."""
    print("\n🔧 [0/5] Setting up channel and persona in DB...")

    channel_info = channel_config.get("channel", {})
    persona_config = channel_config.get("persona", {})
    filtering_config = channel_config.get("filtering", {})
    topic_collection = channel_config.get("topic_collection", {})
    content_config = channel_config.get("content", {})
    operation_config = channel_config.get("operation", {})

    channel_name = channel_info.get("name", "Default Channel")

    # Check if channel exists
    result = await session.execute(select(Channel).where(Channel.name == channel_name))
    channel = result.scalar_one_or_none()

    if channel:
        print(f"   ✅ Found existing channel: {channel.name} (id={channel.id})")
    else:
        channel = Channel(
            id=uuid.uuid4(),
            name=channel_name,
            description=channel_info.get("description"),
            youtube_channel_id=channel_info.get("youtube", {}).get("channel_id") or None,
            youtube_handle=channel_info.get("youtube", {}).get("handle"),
            status=ChannelStatus.ACTIVE,
            topic_config={
                "region_weights": topic_collection.get("region_weights", {}),
                "enabled_sources": topic_collection.get("enabled_sources", []),
                "source_overrides": topic_collection.get("source_overrides", {}),
            },
            source_config=filtering_config,
            content_config=content_config,
            operation_config=operation_config,
            default_hashtags=channel_config.get("upload", {}).get("default_hashtags"),
        )
        session.add(channel)
        await session.flush()
        print(f"   ✅ Created new channel: {channel.name} (id={channel.id})")

    # Check if persona exists
    result = await session.execute(select(Persona).where(Persona.channel_id == channel.id))
    persona = result.scalar_one_or_none()

    if persona:
        print(f"   ✅ Found existing persona: {persona.name}")
    else:
        communication = persona_config.get("communication", {})
        perspective = persona_config.get("perspective", {})
        voice_config = persona_config.get("voice", {})
        speech_patterns = communication.get("speech_patterns", {})

        persona = Persona(
            id=uuid.uuid4(),
            channel_id=channel.id,
            name=persona_config.get("name", channel_name),
            tagline=persona_config.get("tagline"),
            description=persona_config.get("description"),
            expertise=perspective.get("core_values", []),
            voice_gender=voice_config.get("gender"),
            tts_service=TTSService(voice_config.get("service", "edge-tts")),
            voice_id=voice_config.get("voice_id"),
            voice_settings=voice_config.get("settings"),
            communication_style={
                "tone": communication.get("tone"),
                "formality": communication.get("formality"),
                "sentence_endings": speech_patterns.get("sentence_endings", []),
                "connectors": speech_patterns.get("connectors", []),
                "emphasis_words": speech_patterns.get("emphasis_words", []),
                "avoid_words": communication.get("avoid_patterns", {}).get("words", []),
            },
            perspective={
                "approach": perspective.get("approach"),
                "core_values": perspective.get("core_values", []),
                "contrarian_views": perspective.get("contrarian_views", []),
            },
        )
        session.add(persona)
        await session.flush()
        print(f"   ✅ Created new persona: {persona.name}")

    await session.commit()
    return channel, persona


# =============================================================================
# Step 2: Topic Collection (uses TopicCollectionPipeline service)
# =============================================================================


async def collect_topics(
    session: AsyncSession,
    channel: Channel,
    channel_config: dict[str, Any],
) -> list[Topic]:
    """Collect and process topics using TopicCollectionPipeline service."""
    print("\n📡 [1/5] Collecting topics using TopicCollectionPipeline...")

    # Create pipeline (no redis for demo - skip deduplication)
    pipeline = TopicCollectionPipeline(session=session)

    # Create config from channel YAML
    config = CollectionConfig.from_channel_config(channel_config)

    # Run pipeline
    topics, stats = await pipeline.collect_for_channel(channel, config)

    # Print stats
    print("   📊 Collection stats:")
    print(f"      Raw: {stats.total_collected}")
    print(f"      Normalized: {stats.normalized_count}")
    print(f"      Filtered: {stats.filtered_count}")
    print(f"      Saved: {stats.saved_count}")

    if stats.errors:
        print(f"   ⚠️ Errors: {len(stats.errors)}")

    # If no new topics, try to get existing unused topics from DB
    if not topics:
        print("   📌 No new topics, checking existing DB topics...")
        result = await session.execute(
            select(Topic)
            .where(Topic.channel_id == channel.id)
            .where(Topic.status != TopicStatus.USED)
            .order_by(Topic.created_at.desc())
            .limit(5)
        )
        topics = list(result.scalars().all())
        print(f"   ✅ Found {len(topics)} existing topics in DB")

    return topics


# =============================================================================
# Step 3: Script Generation (uses ScriptGenerator service)
# =============================================================================


async def generate_script(
    session: AsyncSession,
    topic: Topic,
    channel: Channel,
) -> Script:
    """Generate script using ScriptGenerator service."""
    print(f"\n📝 [2/5] Generating script for: {topic.title_normalized[:50]}...")

    # Get ScriptGenerator from DI container
    script_generator = container.services.script_generator()

    print("   🤖 Using ScriptGenerator service")
    print(f"   📋 Topic ID: {topic.id}")

    try:
        script = await script_generator.generate_scene_script(
            topic_id=topic.id,
            channel_id=channel.id,
        )

        print(f"   ✅ Script generated: {script.id}")
        print(f"      📊 Quality: passed={script.quality_passed}")
        print(f"      ⏱️ Duration: {script.estimated_duration}s")

        if script.scenes:
            print(f"      🎬 Scenes: {len(script.scenes)}")

        topic.status = TopicStatus.USED
        await session.commit()

        return script

    except Exception as e:
        print(f"   ⚠️ ScriptGenerator failed: {e}")
        logger.error("Script generation failed", exc_info=True)

        # Fallback script
        print("   📌 Creating fallback script...")
        fallback_text = f"""이거 모르면 진짜 손해에요!

{topic.title_normalized}.
근데 이게 왜 중요하냐면, AI 기술이 진짜 빠르게 바뀌고 있거든요.

솔직히 제 생각엔 이게 시작일 뿐이에요.

이런 소식 더 보고 싶으면 구독 눌러줘요!"""

        script = Script(
            id=uuid.uuid4(),
            channel_id=channel.id,
            topic_id=topic.id,
            script_text=fallback_text,
            estimated_duration=40,
            word_count=len(fallback_text.split()),
            style_score=0.7,
            hook_score=0.6,
            forbidden_words=[],
            quality_passed=True,
            generation_model="fallback",
            context_chunks_used=0,
            generation_metadata={"fallback": True, "reason": str(e)},
            status=ScriptStatus.GENERATED,
            scenes=[
                {"scene_type": "hook", "text": "이거 모르면 진짜 손해에요!", "keyword": "AI"},
                {"scene_type": "content", "text": f"{topic.title_normalized}.", "keyword": "tech"},
                {
                    "scene_type": "commentary",
                    "text": "솔직히 제 생각엔 이게 시작일 뿐이에요.",
                    "keyword": "opinion",
                },
                {
                    "scene_type": "conclusion",
                    "text": "이런 소식 더 보고 싶으면 구독 눌러줘요!",
                    "keyword": "CTA",
                },
            ],
        )
        session.add(script)
        topic.status = TopicStatus.USED
        await session.commit()
        await session.refresh(script)

        print(f"   ✅ Fallback script created: {script.id}")
        return script


# =============================================================================
# Step 4-5: Video Generation (uses VideoGenerationPipeline service)
# =============================================================================


async def generate_video(
    session: AsyncSession,
    script: Script,
    channel: Channel,
    persona: Persona,
    channel_config: dict[str, Any],
) -> Path:
    """Generate video using VideoGenerationPipeline service."""
    print(f"\n🎬 [3/5] Generating video for script: {script.id}...")

    # Get VideoGenerationPipeline from DI container
    video_pipeline = container.services.video_pipeline()

    voice_id = persona.voice_id or "ko-KR-InJoonNeural"
    tts_provider = persona.tts_service.value if persona.tts_service else "edge-tts"

    print(f"   🎤 TTS: {tts_provider}, voice: {voice_id}")

    content_config = channel_config.get("content", {})
    template_name = content_config.get("template", "korean_shorts_standard")

    # Persona style for visual differentiation
    from app.config.persona import PersonaStyleConfig

    persona_style = None
    if persona.communication_style:
        accent_color = content_config.get("subtitle", {}).get("accent_color", "#00d4ff")
        persona_style = PersonaStyleConfig(
            accent_color=accent_color,
            persona_border=True,
            persona_border_color=accent_color,
        )

    try:
        if script.has_scenes:
            print("   🎭 Using scene-based generation")
            scene_script = script.get_scene_script()

            if scene_script:
                result = await video_pipeline.generate_from_scenes(
                    script=script,
                    scene_script=scene_script,
                    voice_id=voice_id,
                    tts_provider=tts_provider,
                    template_name=template_name,
                    persona_style=persona_style,
                )
            else:
                result = await video_pipeline.generate(
                    script=script,
                    voice_id=voice_id,
                    tts_provider=tts_provider,
                    template_name=template_name,
                )
        else:
            result = await video_pipeline.generate(
                script=script,
                voice_id=voice_id,
                tts_provider=tts_provider,
                template_name=template_name,
            )

        print("\n   ✅ Video generated!")
        print(f"      📹 Path: {result.video_path}")
        print(f"      ⏱️ Duration: {result.duration_seconds:.1f}s")
        print(f"      📦 Size: {result.file_size_bytes / 1024 / 1024:.1f} MB")

        # Save Video to DB
        print("\n   💾 [4/5] Saving video to database...")
        from app.models.video import Video, VideoStatus

        video = Video(
            id=uuid.uuid4(),
            channel_id=channel.id,
            script_id=script.id,
            video_path=str(result.video_path),
            thumbnail_path=str(result.thumbnail_path),
            audio_path=str(result.audio_path),
            subtitle_path=str(result.subtitle_path) if result.subtitle_path else None,
            duration_seconds=result.duration_seconds,
            file_size_bytes=result.file_size_bytes,
            resolution="1080x1920",
            fps=30,
            tts_service=result.tts_service,
            tts_voice_id=result.tts_voice_id,
            visual_sources=result.visual_sources,
            generation_time_seconds=result.generation_time_seconds,
            generation_metadata={"template": template_name, "scene_based": script.has_scenes},
            status=VideoStatus.GENERATED,
        )
        session.add(video)
        await session.commit()
        print(f"   ✅ Video saved to DB: {video.id}")

        return result.video_path

    except Exception as e:
        print(f"   ⚠️ VideoGenerationPipeline failed: {e}")
        logger.error("Video generation failed", exc_info=True)
        raise


# =============================================================================
# Main Pipeline
# =============================================================================


async def main() -> None:
    """Run full production pipeline."""
    print("=" * 70)
    print("🚀 BSForge Full Production Pipeline")
    print("=" * 70)

    config_path = Path(sys.argv[1] if len(sys.argv) > 1 else "config/channels/ai_tech.yaml")

    if not config_path.exists():
        print(f"❌ Channel config not found: {config_path}")
        return

    channel_config = load_channel_config(config_path)
    channel_name = channel_config.get("channel", {}).get("name", "Unknown")
    print(f"\n📺 Channel: {channel_name}")
    print(f"📄 Config: {config_path}")

    db_session_factory = container.infrastructure.db_session_factory()

    async with db_session_factory() as session:
        try:
            # Step 0: Setup channel and persona
            channel, persona = await setup_channel_and_persona(session, channel_config)

            # Step 1: Collect topics (uses TopicCollectionPipeline)
            topics = await collect_topics(session, channel, channel_config)

            if not topics:
                print("\n❌ No topics collected")
                return

            topic = topics[0]
            print(f"\n📰 Selected: {topic.title_normalized}")

            # Step 2: Generate script (uses ScriptGenerator)
            script = await generate_script(session, topic, channel)

            # Steps 3-4: Generate video (uses VideoGenerationPipeline)
            video_path = await generate_video(session, script, channel, persona, channel_config)

            # Summary
            print("\n" + "=" * 70)
            print("✅ [5/5] Pipeline complete!")
            print("=" * 70)
            print(f"📺 Channel: {channel.name}")
            print(f"📰 Topic: {topic.title_normalized[:50]}...")
            print(f"📝 Script: {script.id}")
            print(f"🎬 Video: {video_path}")
            print("=" * 70)

        except Exception as e:
            print(f"\n❌ Pipeline failed: {e}")
            logger.error("Pipeline failed", exc_info=True)
            raise


if __name__ == "__main__":
    asyncio.run(main())
