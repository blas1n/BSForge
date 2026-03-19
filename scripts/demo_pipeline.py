#!/usr/bin/env python
"""BSForge Demo Pipeline: Channel Config → Real Topics → Script → Video.

Channel-config-driven pipeline that collects real topics from Reddit/RSS,
normalizes with LLM, and generates video from actual current content.

Phases:
0. Load channel config YAML (persona, sources, content settings)
1. Collect real topics from Reddit + HN RSS (no API keys)
2. Normalize best topic with LLM (translate, classify)
3. Generate script with persona + real data
4. TTS with persona voice settings
5. Subtitles → Visuals → Remotion composition

Run with: uv run python scripts/demo_pipeline.py [config_path]
"""

from __future__ import annotations

import asyncio
import random
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from app.config.persona import PersonaConfig
from app.config.video import CompositionConfig, SubtitleConfig, VisualConfig, WanConfig
from app.core.config import get_config
from app.core.dependencies import create_llm_client, create_prompt_manager
from app.core.logging import get_logger, setup_logging
from app.core.template_loader import load_template
from app.infrastructure.http_client import HTTPClient
from app.models.scene import Scene, SceneScript, SceneType
from app.services.collector.base import RawTopic
from app.services.collector.sources.factory import collect_from_sources
from app.services.generator.ffmpeg import FFmpegWrapper
from app.services.generator.remotion_compositor import RemotionCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.templates import ASSTemplateLoader
from app.services.generator.tts.base import TTSSynthesisConfig
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.tts.utils import concatenate_scene_audio
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.wan_video_source import WanVideoSource
from app.services.script_generator import ScriptGenerator

setup_logging()
logger = get_logger(__name__)

OUTPUT_DIR = Path("/tmp/bsforge_demo")
DEFAULT_CONFIG = Path("config/channels/demo_tech.yaml")

# Fallback script when both collection and LLM are unavailable
FALLBACK_SCENES = [
    Scene(
        scene_type=SceneType.HOOK,
        text="여러분, AI가 코딩을 대체한다고요?",
        visual_keyword="programmer typing dark room neon",
    ),
    Scene(
        scene_type=SceneType.CONTENT,
        text="최근 클로드 코드가 출시되면서 개발자들 사이에서 난리가 났습니다.",
        visual_keyword="futuristic hologram technology interface",
    ),
    Scene(
        scene_type=SceneType.CONTENT,
        text="실제로 간단한 버그 수정부터 리팩토링까지 혼자서 척척 해냅니다.",
        visual_keyword="code screen scrolling fast closeup",
    ),
    Scene(
        scene_type=SceneType.COMMENTARY,
        text="근데 솔직히 말해서, 아직 시니어 개발자를 대체하긴 어렵습니다.",
        visual_keyword="man thinking office window cityscape",
    ),
    Scene(
        scene_type=SceneType.CONCLUSION,
        text="도구는 도구일 뿐, 결국 판단은 사람의 몫입니다.",
        visual_keyword="team collaboration whiteboard brainstorm",
    ),
]
FALLBACK_HEADLINE = "AI가 코딩을 대체한다고?"


def load_channel_config(config_path: Path) -> dict[str, Any]:
    """Load and parse a channel config YAML file.

    Args:
        config_path: Path to channel config YAML

    Returns:
        Parsed config dict with channel, persona, topic_collection, content sections

    Raises:
        FileNotFoundError: If config file does not exist
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Channel config not found: {config_path}")
    return yaml.safe_load(config_path.read_text())


def pick_best_topic(topics: list[RawTopic]) -> RawTopic | None:
    """Select the highest-engagement topic from collected raw topics.

    Ranks by score + comments. Returns None for empty list.

    Args:
        topics: List of raw topics from sources

    Returns:
        Best topic or None if list is empty
    """
    if not topics:
        return None

    def engagement_score(topic: RawTopic) -> float:
        score = topic.metrics.get("score", 0) or 0
        comments = topic.metrics.get("comments", 0) or 0
        return float(score) + float(comments) * 0.5

    return max(topics, key=engagement_score)


async def collect_topics(
    topic_config: dict[str, Any],
    filtering: dict[str, Any] | None = None,
) -> list[RawTopic]:
    """Collect real topics from configured sources (Reddit, RSS).

    Args:
        topic_config: topic_collection section from channel config
        filtering: Optional filtering config (include/exclude lists)

    Returns:
        List of collected RawTopic objects
    """
    sources = topic_config.get("sources", [])
    source_overrides = topic_config.get("source_overrides", {})

    http_client = HTTPClient()
    try:
        raw_topics = await collect_from_sources(
            enabled_sources=sources,
            http_client=http_client,
            source_overrides=source_overrides,
        )
    finally:
        await http_client.close()

    # Apply basic filtering if configured
    if filtering:
        exclude_terms = [t.lower() for t in filtering.get("exclude", [])]
        if exclude_terms:
            raw_topics = [
                t for t in raw_topics if not any(term in t.title.lower() for term in exclude_terms)
            ]

    return raw_topics


async def normalize_topic(
    raw: RawTopic,
    target_language: str = "ko",
) -> dict[str, Any]:
    """Normalize a raw topic using LLM (translate, classify, summarize).

    Args:
        raw: Raw topic to normalize
        target_language: Target language code

    Returns:
        Dict with title_translated, summary, terms keys
    """
    import uuid

    from app.services.collector.normalizer import TopicNormalizer

    llm_client = create_llm_client()
    prompt_manager = create_prompt_manager()
    normalizer = TopicNormalizer(llm_client=llm_client, prompt_manager=prompt_manager)

    normalized = await normalizer.normalize(
        raw=raw,
        source_id=uuid.uuid4(),
        target_language=target_language,
    )

    return {
        "title_original": normalized.title_original,
        "title_translated": normalized.title_translated,
        "summary": normalized.summary,
        "terms": normalized.terms,
    }


def _make_visual_manager(http_client: HTTPClient) -> VisualSourcingManager:
    """Create VisualSourcingManager with Pexels → Wan → solid-color priority."""
    pexels = PexelsClient()
    wan = WanVideoSource(http_client=http_client, config=WanConfig())
    visual_config = VisualConfig(metadata_score_threshold=0.1)
    return VisualSourcingManager(
        http_client=http_client,
        config=visual_config,
        pexels_client=pexels,
        wan_video_source=wan,
    )


async def main() -> None:
    """Run the channel-config-driven demo pipeline."""
    # Parse optional config path from CLI args
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG

    print("=" * 60)
    print("BSForge Demo Pipeline (Channel-Driven)")
    print("Config → Topics → Script → TTS → Subtitles → Visuals → Video")
    print("=" * 60)

    # Check prerequisites
    if not shutil.which("ffmpeg"):
        print("\nERROR: FFmpeg is required.")
        sys.exit(1)

    remotion_dir = Path("/workspace/remotion")
    if not (remotion_dir / "node_modules").exists():
        print("\nERROR: Remotion node_modules not found. Run: cd remotion && npm install")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================
    # Phase 0: Load Channel Config
    # ========================================
    print(f"\n[0/6] Loading channel config: {config_path}")

    channel_config = load_channel_config(config_path)
    persona = PersonaConfig(**channel_config["persona"])
    topic_config = channel_config["topic_collection"]
    content_config = channel_config.get("content", {})
    filtering_config = channel_config.get("filtering")

    print(f"   Channel: {channel_config['channel']['name']}")
    print(f"   Persona: {persona.name} — {persona.tagline}")
    print(f"   Sources: {topic_config['sources']}")
    print(f"   Target duration: {content_config.get('target_duration', 30)}s")

    # ========================================
    # Phase 1: Collect Real Topics
    # ========================================
    print("\n[1/6] Collecting real topics...")

    topic_title = None
    topic_summary = None
    topic_terms: list[str] = []

    try:
        raw_topics = await collect_topics(topic_config, filtering_config)
        print(f"   Collected {len(raw_topics)} topics from {topic_config['sources']}")

        best = pick_best_topic(raw_topics)
        if best:
            print(f"   Best topic: {best.title[:60]}")
            print(
                f"   Score: {best.metrics.get('score', 0)}, "
                f"Comments: {best.metrics.get('comments', 0)}"
            )

            # Phase 2: Normalize
            print("\n[2/6] Normalizing topic...")
            config = get_config()
            if config.llm_api_key:
                target_lang = topic_config.get("target_language", "ko")
                normalized = await normalize_topic(best, target_lang)
                topic_title = normalized["title_translated"] or normalized["title_original"]
                topic_summary = normalized["summary"]
                topic_terms = normalized["terms"]
                print(f"   Normalized title: {topic_title}")
                print(f"   Summary: {topic_summary[:80]}...")
                print(f"   Terms: {topic_terms}")
            else:
                # No LLM key — use raw topic title directly
                topic_title = best.title
                topic_summary = best.content or best.title
                topic_terms = []
                print(f"   LLM_API_KEY not set, using raw title: {topic_title}")
        else:
            print("   No topics found after filtering")
    except Exception as e:
        print(f"   Topic collection failed: {e}")
        print("   Will use fallback script")

    # ========================================
    # Phase 3: Script Generation
    # ========================================
    print("\n[3/6] Generating script...")

    scene_script = None
    config = get_config()

    if topic_title and config.llm_api_key:
        try:
            llm_client = create_llm_client()
            prompt_manager = create_prompt_manager()
            generator = ScriptGenerator(llm_client=llm_client, prompt_manager=prompt_manager)

            target_duration = content_config.get("target_duration", 30)
            result = await generator.generate(
                topic_title=topic_title,
                topic_summary=topic_summary or topic_title,
                topic_terms=topic_terms,
                persona=persona,
                target_duration=target_duration,
            )

            scene_script = result.scene_script
            print(f"   LLM script: {len(scene_script.scenes)} scenes")
            print(f"   Headline: {scene_script.headline}")
            print(f"   Model: {result.model}")
        except Exception as e:
            print(f"   Script generation failed: {e}")

    if scene_script is None:
        print("   Using fallback script")
        scene_script = SceneScript(scenes=FALLBACK_SCENES, headline=FALLBACK_HEADLINE)

    scene_script.apply_recommended_transitions()

    scenes = scene_script.scenes
    print(f"   Scenes: {len(scenes)}")
    for i, s in enumerate(scenes):
        print(f"   {i + 1}. [{s.scene_type.value}] {s.text[:50]}...")

    # Load video template
    template_name = content_config.get("video_template", "korean_shorts_standard")
    video_template = load_template(template_name)
    print(f"   Template: {template_name}")

    # ========================================
    # Phase 4: TTS Generation (persona voice settings)
    # ========================================
    print("\n[4/6] Generating TTS audio...")

    ffmpeg_wrapper = FFmpegWrapper()
    tts_engine = EdgeTTSEngine(ffmpeg_wrapper=ffmpeg_wrapper)
    tts_config = TTSSynthesisConfig(
        voice_id=persona.voice.voice_id,
        speed=persona.voice.settings.speed,
    )

    scene_tts_results = await tts_engine.synthesize_scenes(
        scenes=scenes,
        config=tts_config,
        output_dir=OUTPUT_DIR / "audio_scenes",
    )

    for i, r in enumerate(scene_tts_results):
        print(f"   Scene {i + 1}: {r.duration_seconds:.1f}s -> {r.audio_path.name}")

    combined_tts = await concatenate_scene_audio(
        scene_results=scene_tts_results,
        output_path=OUTPUT_DIR / "combined_audio",
        ffmpeg_wrapper=ffmpeg_wrapper,
    )
    print(f"   Combined audio: {combined_tts.duration_seconds:.1f}s")

    # ========================================
    # Phase 5: Subtitles + Visuals
    # ========================================
    print("\n[5/6] Generating subtitles + visuals...")

    subtitle_gen = SubtitleGenerator(
        config=SubtitleConfig(),
        composition_config=CompositionConfig(),
        template_loader=ASSTemplateLoader(),
    )

    subtitle_file = subtitle_gen.generate_from_scene_results(
        scene_results=scene_tts_results,
        scenes=scenes,
    )

    subtitle_path = OUTPUT_DIR / "subtitles.ass"
    subtitle_gen.to_ass(subtitle_file, subtitle_path)
    print(f"   Subtitle segments: {len(subtitle_file.segments)}")

    # Visuals — Pexels HD → Wan AI video → solid-color fallback
    visuals_dir = OUTPUT_DIR / "visuals"
    http_client = HTTPClient()
    visual_manager = _make_visual_manager(http_client)

    scene_visuals = await visual_manager.source_visuals_for_scenes(
        scenes=scenes,
        scene_results=scene_tts_results,
        output_dir=visuals_dir,
        orientation="portrait",
    )

    for i, sv in enumerate(scene_visuals):
        src = sv.asset.source if sv.asset else "none"
        name = sv.asset.path.name if sv.asset and sv.asset.path else "no-file"
        print(f"   Visual {i + 1}: {src} -> {name}")

    await visual_manager.close()
    await http_client.close()

    # ========================================
    # Phase 6: Remotion Composition
    # ========================================
    print("\n[6/6] Composing video with Remotion...")

    bgm_path: Path | None = None
    bgm_candidates = list(Path("data/bgm").glob("*.mp3")) if Path("data/bgm").exists() else []
    if bgm_candidates:
        bgm_path = random.choice(bgm_candidates)
        print(f"   BGM: {bgm_path.name}")
    else:
        print("   BGM: none (place .mp3 files in data/bgm/ to enable)")

    compositor = RemotionCompositor(config=CompositionConfig())
    final_path = OUTPUT_DIR / "final_video"

    result = await compositor.compose_scenes(
        scenes=scenes,
        scene_tts_results=scene_tts_results,
        scene_visuals=scene_visuals,
        combined_audio_path=combined_tts.audio_path,
        subtitle_file=subtitle_path,
        output_path=final_path,
        headline=scene_script.headline,
        subtitle_data=subtitle_file,
        video_template=video_template,
        background_music_path=bgm_path,
    )

    # ========================================
    # Done
    # ========================================
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"\n   Video: {result.video_path}")
    print(f"   Duration: {result.duration_seconds:.1f}s")
    print(f"   Size: {result.file_size_bytes / 1024 / 1024:.1f} MB")
    print(f"   Resolution: {result.resolution}")
    print(f"   FPS: {result.fps}")
    print(f"\n   Output dir: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
