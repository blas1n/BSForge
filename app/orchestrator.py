"""Main automation orchestrator.

Replaces Celery workers with a simple sequential pipeline:
collect topics → generate script → generate video → upload

Each channel is processed independently. Each topic produces one video.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.persona import PersonaConfig
from app.core.config import get_config
from app.core.database import async_session_maker, close_db
from app.core.dependencies import (
    create_collector_pipeline,
    create_http_client,
    create_llm_client,
    create_prompt_manager,
    create_script_generator,
    create_upload_pipeline,
    create_video_pipeline,
)
from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.llm import LLMClient
from app.models.channel import Channel, ChannelStatus
from app.models.script import Script, ScriptStatus
from app.models.topic import Topic
from app.prompts.manager import PromptManager
from app.services.collector.pipeline import CollectionConfig
from app.services.script_generator import ScriptGenerator

logger = get_logger(__name__)


async def get_active_channels(session: AsyncSession) -> list[Channel]:
    """Load all active channels with their personas."""
    result = await session.execute(
        select(Channel)
        .where(Channel.status == ChannelStatus.ACTIVE)
        .options(selectinload(Channel.persona))
    )
    return list(result.scalars().all())


async def process_channel(channel: Channel) -> int:
    """Run the full pipeline for one channel.

    Steps:
    1. Collect topics
    2. For each new topic: generate script → generate video → upload

    Args:
        channel: Active channel to process

    Returns:
        Number of videos produced
    """
    logger.info("processing_channel", channel=channel.name, channel_id=str(channel.id))

    # Shared dependencies for this run
    http_client = create_http_client()
    llm_client = create_llm_client()
    prompt_manager = create_prompt_manager()

    videos_produced = 0

    try:
        # Step 1: Collect topics
        topics = await _collect_topics(channel, http_client, llm_client, prompt_manager)

        if not topics:
            logger.info("no_new_topics", channel=channel.name)
            return 0

        # Step 2: Process each topic individually (1 topic = 1 video)
        script_generator = create_script_generator(
            llm_client=llm_client, prompt_manager=prompt_manager
        )

        for topic in topics:
            try:
                produced = await _process_topic(
                    channel=channel,
                    topic=topic,
                    script_generator=script_generator,
                    http_client=http_client,
                )
                if produced:
                    videos_produced += 1
            except Exception:
                logger.exception(
                    "topic_processing_failed",
                    channel=channel.name,
                    topic=topic.title,
                )
                continue

    finally:
        await http_client.close()

    logger.info(
        "channel_processing_complete",
        channel=channel.name,
        videos_produced=videos_produced,
    )
    return videos_produced


async def _collect_topics(
    channel: Channel,
    http_client: HTTPClient,
    llm_client: LLMClient,
    prompt_manager: "PromptManager",
) -> list[Topic]:
    """Collect topics for a channel."""
    # Build collection config from channel settings
    channel_config = {
        "topic_collection": channel.topic_config or {},
        "filtering": channel.content_config.get("filtering", {}) if channel.content_config else {},
    }
    config = CollectionConfig.from_channel_config(channel_config)

    if not config.sources:
        logger.warning("no_sources_configured", channel=channel.name)
        return []

    async with async_session_maker() as session:
        pipeline = await create_collector_pipeline(
            session=session,
            http_client=http_client,
            llm_client=llm_client,
            prompt_manager=prompt_manager,
        )
        topics, stats = await pipeline.collect_for_channel(channel, config)

    logger.info(
        "topics_collected",
        channel=channel.name,
        collected=stats.total_collected,
        saved=stats.saved_count,
    )
    return topics


async def _process_topic(
    channel: Channel,
    topic: Topic,
    script_generator: ScriptGenerator,
    http_client: HTTPClient,
) -> bool:
    """Process a single topic: script → video → upload.

    Returns True if a video was produced.
    """
    logger.info("processing_topic", topic=topic.title, channel=channel.name)

    # Step 1: Generate script
    persona_config = _build_persona_config(channel)

    script_result = await script_generator.generate(
        topic_title=topic.title,
        topic_summary=topic.summary or "",
        topic_terms=topic.terms or [],
        persona=persona_config,
    )

    # Save script to DB
    async with async_session_maker() as session:
        script = Script(
            id=uuid.uuid4(),
            channel_id=channel.id,
            topic_id=topic.id,
            script_text=script_result.raw_response,
            headline=script_result.scene_script.headline,
            scenes=[s.__dict__ for s in script_result.scene_script.scenes],
            generation_model=script_result.model,
            status=ScriptStatus.GENERATED,
        )
        session.add(script)
        await session.commit()
        await session.refresh(script)

        script_id = script.id

    logger.info(
        "script_generated",
        topic=topic.title,
        headline=script_result.scene_script.headline,
        scenes=len(script_result.scene_script.scenes),
    )

    # Step 2: Generate video
    video_pipeline = create_video_pipeline(http_client=http_client)

    async with async_session_maker() as session:
        script = await session.get(Script, script_id)
        if not script:
            logger.error("script_not_found", script_id=str(script_id))
            return False

        scene_script = script.get_scene_script()
        voice_id = _get_voice_id(channel)
        tts_provider = _get_tts_provider(channel)

        video_result = await video_pipeline.generate(
            script=script,
            scene_script=scene_script,
            voice_id=voice_id,
            tts_provider=tts_provider,
        )

    logger.info(
        "video_generated",
        topic=topic.title,
        duration=video_result.duration_seconds,
        path=str(video_result.video_path),
    )

    # Step 3: Upload (if auto-upload enabled)
    config = get_config()
    if config.enable_auto_upload:
        try:
            # TODO: Wire up upload pipeline with video_id once video DB record is created
            create_upload_pipeline()
            logger.info("auto_upload_skipped", reason="upload_pipeline_needs_video_id")
        except Exception:
            logger.exception("upload_failed", topic=topic.title)

    return True


def _build_persona_config(channel: Channel) -> PersonaConfig | None:
    """Build PersonaConfig from channel's persona model."""
    from app.config.persona import CommunicationStyle, Perspective, VoiceConfig

    if not channel.persona:
        return None

    persona = channel.persona
    try:
        # Build VoiceConfig from persona DB fields
        voice = VoiceConfig(
            gender=persona.voice_gender or "male",
            service=persona.tts_service or "edge-tts",
            voice_id=persona.voice_id or "ko-KR-InJoonNeural",
        )

        # Build CommunicationStyle from persona JSONB
        comm_data = persona.communication_style or {}
        communication = CommunicationStyle(
            tone=comm_data.get("tone", "friendly"),
            formality=comm_data.get("formality", "semi-formal"),
        )

        # Build Perspective from persona JSONB
        persp_data = persona.perspective or {}
        perspective = Perspective(
            core_values=persp_data.get("core_values", []),
            contrarian_views=persp_data.get("contrarian_views", []),
        )

        return PersonaConfig(
            name=persona.name,
            tagline=persona.tagline or "",
            voice=voice,
            communication=communication,
            perspective=perspective,
        )
    except Exception:
        logger.exception("persona_config_build_failed", channel=channel.name)
        return None


def _get_voice_id(channel: Channel) -> str | None:
    """Get voice ID from channel persona."""
    if channel.persona and channel.persona.voice_id:
        return channel.persona.voice_id
    return None


def _get_tts_provider(channel: Channel) -> str | None:
    """Get TTS provider from channel persona."""
    if channel.persona and channel.persona.tts_service:
        return channel.persona.tts_service
    return None


async def run_once() -> None:
    """Run the pipeline once for all active channels."""
    logger.info("orchestrator_run_start")
    start = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        channels = await get_active_channels(session)

    if not channels:
        logger.info("no_active_channels")
        return

    logger.info("active_channels_found", count=len(channels))

    total_videos = 0
    for channel in channels:
        try:
            count = await process_channel(channel)
            total_videos += count
        except Exception:
            logger.exception("channel_failed", channel=channel.name)
            continue

    elapsed = (datetime.now(tz=UTC) - start).total_seconds()
    logger.info(
        "orchestrator_run_complete",
        channels_processed=len(channels),
        videos_produced=total_videos,
        elapsed_seconds=elapsed,
    )


async def run_scheduler(interval_hours: int = 6) -> None:
    """Run the pipeline on a schedule.

    Simple loop-based scheduler. For production, consider APScheduler.

    Args:
        interval_hours: Hours between runs
    """
    logger.info("scheduler_started", interval_hours=interval_hours)

    while True:
        try:
            await run_once()
        except Exception:
            logger.exception("scheduler_run_failed")

        logger.info("scheduler_sleeping", hours=interval_hours)
        await asyncio.sleep(interval_hours * 3600)


async def main() -> None:
    """Entry point for the orchestrator."""
    config = get_config()
    logger.info(
        "orchestrator_starting",
        env=config.app_env,
    )

    try:
        await run_scheduler()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
