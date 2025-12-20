#!/usr/bin/env python
"""Full pipeline demo: Topic Collection → Script → Video Generation.

This script demonstrates the complete BSForge pipeline using channel config:
1. Collect topics from configured sources (HackerNews, Reddit)
2. Normalize, filter, and score topics
3. Generate scene-based script from top topic using LLM
4. Generate video with TTS, subtitles, and visuals

All settings are driven by channel config YAML.

Run with: uv run python scripts/demo_full_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

# ============================================
# CONFIGURABLE VARIABLES
# ============================================

CHANNEL_CONFIG_PATH = Path(__file__).parent.parent / "config/channels/subculture.yaml"
VIDEO_TEMPLATE_NAME = "korean_shorts_standard"
OUTPUT_DIR = Path("/tmp/bsforge_full_demo")

# ============================================


def load_channel_config(config_path: Path) -> dict[str, Any]:
    """Load channel configuration from YAML file.

    Args:
        config_path: Path to channel config YAML file

    Returns:
        Parsed channel configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Channel config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print(f"   Loaded channel config: {config_path.name}")
    print(f"   Channel: {config.get('channel', {}).get('name', 'Unknown')}")

    return config


async def collect_and_process_topics(channel_config: dict[str, Any]) -> dict[str, Any]:
    """Collect and process topics using channel configuration.

    Uses the existing collector services with config-driven settings.
    Clusters similar topics from multiple sources for richer information.

    Args:
        channel_config: Loaded channel configuration dictionary

    Returns:
        Dictionary with 'topic' (best ScoredTopic), 'cluster' (TopicCluster),
        and 'all_clusters' (list)
    """
    from app.config import ScoringConfig
    from app.infrastructure.llm import get_llm_client
    from app.services.collector.clusterer import TopicClusterer
    from app.services.collector.filter import TopicFilter
    from app.services.collector.normalizer import TopicNormalizer
    from app.services.collector.scorer import TopicScorer
    from app.services.collector.sources.factory import create_source

    print("\n" + "=" * 60)
    print("PHASE 1: Topic Collection")
    print("=" * 60)

    # Extract config values
    topic_collection = channel_config.get("topic_collection", {})
    filtering = channel_config.get("filtering", {})

    enabled_sources = topic_collection.get("enabled_sources", ["hackernews"])
    source_overrides = topic_collection.get("source_overrides", {})
    include_terms = filtering.get("include_terms", [])
    exclude_terms = filtering.get("exclude_terms", [])

    print(f"\n   Enabled sources: {enabled_sources}")
    if include_terms:
        print(f"   Include terms: {include_terms[:5]}...")
    if exclude_terms:
        print(f"   Exclude terms: {exclude_terms[:5]}...")

    # 1. Collect raw topics from configured sources
    print("\n[1/4] Collecting raw topics from sources...")
    raw_topics = []

    for source_name in enabled_sources:
        overrides = source_overrides.get(source_name, {})
        print(f"   Fetching from {source_name}...")

        source = create_source(source_name, overrides)
        if source is None:
            print(f"      Unknown or invalid source: {source_name}, skipping...")
            continue

        try:
            topics = await source.collect()
            raw_topics.extend(topics)
            print(f"      Got {len(topics)} topics from {source_name}")
        except Exception as e:
            print(f"      {source_name} failed: {e}")

    if not raw_topics:
        print("   ERROR: No topics collected from any source")
        return {"topic": None, "cluster": None, "all_clusters": []}

    print(f"\n   Total collected: {len(raw_topics)} raw topics")
    for t in raw_topics[:5]:
        print(f"   - [{t.source_id}] {t.title[:50]}...")
    if len(raw_topics) > 5:
        print(f"   ... and {len(raw_topics) - 5} more")

    # 2. Normalize topics using LLM
    print("\n[2/4] Normalizing topics (translation, classification)...")

    llm_client = get_llm_client()
    normalizer = TopicNormalizer(llm_client=llm_client)
    normalized = []

    for topic in raw_topics:
        try:
            source_uuid = uuid4()
            result = await normalizer.normalize(topic, source_uuid)
            normalized.append(result)
            print(f"   - {result.title_normalized[:40]}... → {result.terms[:3]}")
        except Exception as e:
            print(f"   - SKIP: {topic.title[:40]}... (error: {e})")

    if not normalized:
        print("   ERROR: No topics normalized successfully")
        return {"topic": None, "cluster": None, "all_clusters": []}

    # 3. Filter topics using channel config
    print("\n[3/4] Filtering topics using channel config...")

    # Use TopicFilter
    from app.config.filtering import FilteringConfig

    filter_config = FilteringConfig(
        include=include_terms,
        exclude=exclude_terms,
    )
    topic_filter = TopicFilter(filter_config)

    filtered = []
    for topic in normalized:
        result = topic_filter.filter(topic)
        if result.passed:
            filtered.append(topic)
            print(f"   PASS: {topic.title_normalized[:50]}...")
        else:
            print(f"   FAIL: {topic.title_normalized[:50]}...")

    if not filtered:
        print("   WARNING: No topics passed filtering, using all normalized topics")
        filtered = normalized

    # 4. Score topics
    print("\n[4/5] Scoring topics...")

    # Build scoring config with channel's target terms
    scoring_config = ScoringConfig(
        target_categories=[],  # Categories now unified into terms
        target_keywords=include_terms,
    )
    scorer = TopicScorer(config=scoring_config)
    scored = [scorer.score(t) for t in filtered]
    scored.sort(key=lambda x: x.score_total, reverse=True)

    print("\n   Scored topics:")
    for i, topic in enumerate(scored[:5], 1):
        print(f"   {i}. [Score: {topic.score_total}] {topic.title_normalized[:45]}...")

    # 5. Cluster similar topics
    print("\n[5/5] Clustering similar topics from multiple sources...")

    clusterer = TopicClusterer(
        similarity_threshold=0.45,  # Higher threshold for better precision
        min_term_overlap=3,  # Require more term overlap
    )
    clusters = clusterer.cluster(scored, total_sources=len(enabled_sources))

    # Show clustering results
    multi_source_clusters = [c for c in clusters if c.source_count > 1]
    print(f"\n   Total clusters: {len(clusters)}")
    print(f"   Multi-source clusters: {len(multi_source_clusters)}")

    if clusters:
        print("\n   Top clusters:")
        for i, cluster in enumerate(clusters[:5], 1):
            sources_str = ", ".join(cluster.sources)
            topic_count = cluster.topic_count
            print(
                f"   {i}. [{cluster.primary_topic.score_total}점] "
                f"{cluster.primary_topic.title_normalized[:35]}..."
            )
            print(f"      Sources: {sources_str} ({topic_count} topics)")

        # Select best cluster (prefer multi-source if available)
        best_cluster = None
        for cluster in clusters:
            if cluster.source_count > 1:
                best_cluster = cluster
                break
        if not best_cluster:
            best_cluster = clusters[0]

        print(f"\n   Selected cluster: {best_cluster.primary_topic.title_normalized}")
        print(f"   - Sources: {', '.join(best_cluster.sources)}")
        print(f"   - Topics in cluster: {best_cluster.topic_count}")
        print(f"   - Combined terms: {best_cluster.combined_terms[:10]}")

        return {
            "topic": best_cluster.primary_topic,
            "cluster": best_cluster,
            "all_clusters": clusters,
        }

    return {"topic": None, "cluster": None, "all_clusters": []}


async def generate_scene_script(
    topic: Any,
    channel_config: dict[str, Any],
    cluster: Any | None = None,
) -> dict[str, Any]:
    """Generate scene-based script from topic using LLM.

    Args:
        topic: ScoredTopic to generate script for
        channel_config: Loaded channel configuration dictionary
        cluster: Optional TopicCluster with multi-source info

    Returns:
        Dictionary with 'scene_script' (SceneScript) and 'raw_response'
    """
    from app.infrastructure.llm import LLMConfig, get_llm_client
    from app.models.scene import Scene, SceneScript, SceneType, VisualHintType
    from app.prompts.manager import PromptType, get_prompt_manager
    from app.services.rag.utils import build_template_vars_from_channel_config

    print("\n" + "=" * 60)
    print("PHASE 2: Scene-Based Script Generation (LLM)")
    print("=" * 60)

    print(f"\n[1/3] Analyzing topic: {topic.title_normalized}")
    print(f"   Terms: {topic.terms}")

    if cluster and cluster.source_count > 1:
        print("\n   [Multi-Source Coverage]")
        print(f"   - Sources: {', '.join(cluster.sources)}")
        print(f"   - Related topics: {cluster.topic_count - 1}")
        if cluster.related_topics:
            for rt in cluster.related_topics[:3]:
                print(f"     • {rt.title_original[:50]}...")

    # Get prompt manager and LLM client
    prompt_manager = get_prompt_manager()
    llm_client = get_llm_client()

    # Get LLM config from scene_script_generation.yaml
    llm_settings = prompt_manager.get_llm_settings(PromptType.SCRIPT_GENERATION)
    llm_config = LLMConfig.from_prompt_settings(llm_settings)

    print("\n[2/3] Generating scene-based script with LLM...")
    print(f"   Model: {llm_config.model}")
    print(f"   Temperature: {llm_config.temperature}")

    # Build template variables from channel config (with cluster info)
    template_vars = build_template_vars_from_channel_config(channel_config, topic, cluster)

    print(f"   Persona: {template_vars['persona_name']}")
    print(f"   Tone: {template_vars['communication_tone']}")

    # Render prompt and call LLM
    prompt = prompt_manager.render(PromptType.SCRIPT_GENERATION, **template_vars)
    response = await llm_client.complete(
        config=llm_config,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_response = response.content.strip()
    print(f"   LLM Response: {len(raw_response)} characters")

    # Parse JSON response
    print("\n[3/3] Parsing scene response...")

    headline_keyword = None
    headline_hook = None
    raw_scenes = None

    json_obj_match = re.search(r"\{[\s\S]*\}", raw_response)
    if json_obj_match:
        try:
            parsed = json.loads(json_obj_match.group())
            if isinstance(parsed, dict) and "scenes" in parsed:
                headline_keyword = parsed.get("headline_keyword")
                headline_hook = parsed.get("headline_hook")
                raw_scenes = parsed["scenes"]
        except json.JSONDecodeError:
            pass

    if raw_scenes is None:
        json_arr_match = re.search(r"\[[\s\S]*\]", raw_response)
        if json_arr_match:
            try:
                raw_scenes = json.loads(json_arr_match.group())
            except json.JSONDecodeError as e:
                print(f"   ERROR: Failed to parse JSON: {e}")
                return {"scene_script": None, "raw_response": raw_response}

    if not raw_scenes:
        print("   ERROR: No valid scenes in response")
        return {"scene_script": None, "raw_response": raw_response}

    # Parse scenes
    scenes: list[Scene] = []
    for i, raw in enumerate(raw_scenes):
        try:
            scene_type_str = raw.get("scene_type", "content")
            try:
                scene_type = SceneType(scene_type_str)
            except ValueError:
                scene_type = SceneType.CONTENT

            visual_hint_str = raw.get("visual_hint", "stock_image")
            try:
                visual_hint = VisualHintType(visual_hint_str)
            except ValueError:
                visual_hint = VisualHintType.STOCK_IMAGE

            scenes.append(
                Scene(
                    scene_type=scene_type,
                    text=raw.get("text", ""),
                    tts_text=raw.get("tts_text"),
                    keyword=raw.get("keyword"),
                    visual_hint=visual_hint,
                    emphasis_words=raw.get("emphasis_words", []),
                )
            )
        except Exception as e:
            print(f"   WARNING: Failed to parse scene {i}: {e}")

    if not scenes:
        print("   ERROR: No valid scenes parsed")
        return {"scene_script": None, "raw_response": raw_response}

    scene_script = SceneScript(
        scenes=scenes,
        headline_keyword=headline_keyword,
        headline_hook=headline_hook,
    )
    scene_script.apply_recommended_transitions()

    print("\n   Generated SceneScript:")
    print(f"   - Headline: {headline_keyword} / {headline_hook}")
    print(f"   - Scene count: {len(scenes)}")
    print(f"   - Estimated duration: {scene_script.total_estimated_duration:.1f}s")
    print(f"   - Has commentary: {scene_script.has_commentary}")

    print("\n   Scenes:")
    for i, scene in enumerate(scenes, 1):
        emphasis = f" [강조: {', '.join(scene.emphasis_words)}]" if scene.emphasis_words else ""
        print(f"   {i}. [{scene.scene_type.value}] {scene.text[:40]}...{emphasis}")

    return {"scene_script": scene_script, "raw_response": raw_response}


async def generate_video(
    scene_script: Any,
    topic_title: str,
    channel_config: dict[str, Any],
) -> Path | None:
    """Generate video from scene-based script.

    Args:
        scene_script: SceneScript object with scenes
        topic_title: Topic title for thumbnail/overlay
        channel_config: Loaded channel configuration dictionary

    Returns:
        Path to generated video file or None if failed
    """
    from app.config.video import CompositionConfig
    from app.core.template_loader import load_template
    from app.services.generator.compositor import FFmpegCompositor
    from app.services.generator.subtitle import SubtitleGenerator
    from app.services.generator.thumbnail import ThumbnailGenerator
    from app.services.generator.tts.base import TTSConfig
    from app.services.generator.tts.edge import EdgeTTSEngine
    from app.services.generator.tts.utils import concatenate_scene_audio
    from app.services.generator.visual.base import VisualAsset
    from app.services.generator.visual.fallback import FallbackGenerator
    from app.services.generator.visual.manager import SceneVisualResult
    from app.services.generator.visual.pexels import PexelsClient

    print("\n" + "=" * 60)
    print("PHASE 3: Video Generation (Scene-Based)")
    print("=" * 60)

    # Load video template
    print(f"\n[0/6] Loading video template: {VIDEO_TEMPLATE_NAME}")
    try:
        template = load_template(VIDEO_TEMPLATE_NAME)
        print(f"   Template: {template.name}")
        print(f"   Description: {template.description}")
        if template.layout.headline and template.layout.headline.enabled:
            print("   Headline overlay: ENABLED")
        if template.visual_effects.ken_burns_enabled:
            print("   Ken Burns effect: ENABLED")
        if template.visual_effects.color_grading_enabled:
            print("   Color grading: ENABLED")
    except Exception as e:
        print(f"   Warning: Failed to load template '{VIDEO_TEMPLATE_NAME}': {e}")
        print("   Using default settings")
        template = None

    output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)

    # Extract TTS config from channel config
    persona_voice = channel_config.get("persona", {}).get("voice", {})
    voice_id = persona_voice.get("voice_id", "ko-KR-InJoonNeural")
    voice_speed = persona_voice.get("settings", {}).get("speed", 1.1)

    # 1. Per-scene TTS Generation
    print(f"\n[1/6] Generating TTS audio for {len(scene_script.scenes)} scenes...")
    tts_engine = EdgeTTSEngine()
    tts_config = TTSConfig(voice_id=voice_id, speed=voice_speed)
    print(f"   Voice: {voice_id}, Speed: {voice_speed}x")

    scene_tts_results = await tts_engine.synthesize_scenes(
        scenes=scene_script.scenes,
        config=tts_config,
        output_dir=output_dir / "audio_scenes",
    )

    total_duration = sum(r.duration_seconds for r in scene_tts_results)
    print(f"   Scene audio generated: {total_duration:.1f}s total")

    # 2. Concatenate audio
    print("\n[2/6] Concatenating scene audio...")
    combined_tts = await concatenate_scene_audio(
        scene_results=scene_tts_results,
        output_path=output_dir / "combined_audio",
    )
    print(f"   Combined audio: {combined_tts.duration_seconds:.1f}s")

    # 3. Subtitle Generation
    print("\n[3/6] Generating scene-aware subtitles...")
    subtitle_gen = SubtitleGenerator()

    subtitle_file = subtitle_gen.generate_from_scene_results(
        scene_results=scene_tts_results,
        scenes=scene_script.scenes,
        template=template,
    )

    subtitle_path = output_dir / "script_subtitles.ass"
    subtitle_gen.to_ass_with_scene_styles(
        subtitle=subtitle_file,
        output_path=subtitle_path,
        scenes=scene_script.scenes,
        scene_results=scene_tts_results,
        template=template,
    )
    print(f"   Subtitles: {subtitle_path}")
    print(f"   Segments: {len(subtitle_file.segments)}")

    # 4. Per-scene Visual Generation
    print("\n[4/6] Fetching images for each scene from Pexels...")

    downloaded_assets: list[VisualAsset] = []
    used_image_ids: set[str] = set()

    try:
        pexels = PexelsClient()

        for i, (scene, tts_result) in enumerate(
            zip(scene_script.scenes, scene_tts_results, strict=False)
        ):
            search_query = scene.keyword or "technology abstract"
            print(f"   Scene {i + 1} [{scene.scene_type.value}]: Searching '{search_query}'")

            assets = await pexels.search_images(
                search_query,
                max_results=1,
                exclude_ids=used_image_ids,
            )

            for asset in assets:
                try:
                    downloaded = await pexels.download(asset, output_dir / "visuals")
                    downloaded.duration = tts_result.duration_seconds
                    downloaded_assets.append(downloaded)
                    used_image_ids.add(asset.source_id)
                    photographer = downloaded.metadata.get("photographer", "Unknown")
                    print(f"      Downloaded: {downloaded.path.name} ({photographer})")
                except Exception as e:
                    print(f"      Download failed: {e}")

        await pexels.close()
    except Exception as e:
        print(f"   Pexels failed: {e}")

    # Fallback
    if len(downloaded_assets) < len(scene_script.scenes):
        print("   Falling back to fallback images for remaining scenes...")
        fallback_gen = FallbackGenerator()
        while len(downloaded_assets) < len(scene_script.scenes):
            idx = len(downloaded_assets)
            fallback_assets = await fallback_gen.search("fallback", max_results=1)
            if fallback_assets:
                downloaded = await fallback_gen.download(fallback_assets[0], output_dir / "visuals")
                downloaded.duration = scene_tts_results[idx].duration_seconds
                downloaded_assets.append(downloaded)
                print(f"   Added fallback for scene {idx + 1}")

    if not downloaded_assets:
        print("   ERROR: Failed to generate any visuals")
        return None

    print(f"   Total images: {len(downloaded_assets)}")

    # 5. Thumbnail Generation
    print("\n[5/6] Generating thumbnail...")
    thumb_gen = ThumbnailGenerator()
    thumb_path = output_dir / "thumbnail.jpg"

    thumb_title = topic_title[:30] + "..." if len(topic_title) > 30 else topic_title

    # Use first scene's image as thumbnail background
    thumb_background = downloaded_assets[0] if downloaded_assets else None
    if thumb_background:
        print(f"   Using scene 1 image as background: {thumb_background.path.name}")

    # Use thumbnail config from template if available
    thumb_config = template.thumbnail if template else None
    if thumb_config:
        print(f"   Overlay opacity: {thumb_config.overlay_opacity}")

    await thumb_gen.generate(
        title=thumb_title,
        output_path=thumb_path,
        background=thumb_background,
        config_override=thumb_config,
    )
    print(f"   Thumbnail: {thumb_path}")

    # 6. Video Composition
    print("\n[6/6] Composing scene-based video with FFmpeg...")
    print(f"   Using {len(downloaded_assets)} images with Ken Burns zoom effect...")

    # BGM setup from channel config (download if needed)
    from app.config.bgm import BGMConfig, BGMTrack
    from app.services.generator.bgm.downloader import BGMDownloader

    bgm_dict = channel_config.get("bgm", {})
    bgm_path: Path | None = None

    if bgm_dict.get("enabled", False):
        # Build BGMConfig from channel config
        tracks_data = bgm_dict.get("tracks", [])
        bgm_tracks = [
            BGMTrack(name=t["name"], youtube_url=t["youtube_url"])
            for t in tracks_data
            if t.get("name") and t.get("youtube_url")
        ]

        bgm_config = BGMConfig(
            enabled=True,
            tracks=bgm_tracks,
            volume=bgm_dict.get("volume", 0.1),
            cache_dir=bgm_dict.get("cache_dir", "/workspace/data/bgm"),
        )

        if bgm_tracks:
            downloader = BGMDownloader(bgm_config)
            # Download first track (or pick random in future)
            track = bgm_tracks[0]
            cache_path = bgm_config.get_cache_path(track)

            if cache_path.exists():
                bgm_path = cache_path
                print(f"   BGM cached: {track.name}")
            else:
                print(f"   Downloading BGM: {track.name}...")
                try:
                    bgm_path = await downloader.download(track)
                    print(f"   BGM downloaded: {bgm_path.name}")
                except Exception as e:
                    print(f"   BGM download failed: {e}")

    if bgm_path and bgm_path.exists():
        print(f"   Adding background music: {bgm_path.name}")
    else:
        print("   No BGM found, proceeding without background music")
        bgm_path = None

    compositor = FFmpegCompositor(CompositionConfig(), template=template)

    headline_keyword = scene_script.headline_keyword
    headline_hook = scene_script.headline_hook

    current_offset = 0.0
    scene_visuals = []
    for i, (scene, asset, tts_result) in enumerate(
        zip(scene_script.scenes, downloaded_assets, scene_tts_results, strict=False)
    ):
        scene_visuals.append(
            SceneVisualResult(
                scene_index=i,
                scene_type=scene.scene_type.value,
                asset=asset,
                duration=tts_result.duration_seconds,
                start_offset=current_offset,
            )
        )
        current_offset += tts_result.duration_seconds

    final_path = output_dir / "final_shorts.mp4"
    await compositor.compose_scenes(
        scenes=scene_script.scenes,
        scene_tts_results=scene_tts_results,
        scene_visuals=scene_visuals,
        combined_audio_path=combined_tts.audio_path,
        subtitle_file=subtitle_path,
        output_path=final_path,
        background_music_path=bgm_path,
        headline_keyword=headline_keyword,
        headline_hook=headline_hook,
    )

    if final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print("\n   VIDEO GENERATED SUCCESSFULLY!")
        print(f"   Output: {final_path}")
        print(f"   Size: {size_mb:.2f} MB")
        print(f"   Duration: {combined_tts.duration_seconds:.1f} seconds")
        return final_path

    return None


async def main() -> None:
    """Run full pipeline demo."""
    print("=" * 60)
    print("BSForge Full Pipeline Demo (Scene-Based)")
    print("Topic Collection → Scene Script Generation → Video Production")
    print("=" * 60)

    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        print("\nERROR: FFmpeg is required for video generation.")
        print("Please install FFmpeg or use DevContainer.")
        return

    # Load channel config
    print("\n[0/3] Loading channel configuration...")
    try:
        channel_config = load_channel_config(CHANNEL_CONFIG_PATH)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("Please check CHANNEL_CONFIG_PATH at the top of this file.")
        return

    # Phase 1: Topic Collection + Clustering
    result = await collect_and_process_topics(channel_config)

    if not result["topic"]:
        print("\nNo topics available. Demo ended.")
        return

    topic = result["topic"]
    cluster = result.get("cluster")

    # Phase 2: Scene-Based Script Generation (LLM with cluster info)
    script_result = await generate_scene_script(topic, channel_config, cluster)

    if not script_result["scene_script"]:
        print("\nFailed to generate scene script. Demo ended.")
        return

    scene_script = script_result["scene_script"]

    # Phase 3: Video Generation
    title_for_overlay = topic.title_translated or topic.title_normalized
    video_path = await generate_video(
        scene_script,
        title_for_overlay,
        channel_config,
    )

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    if OUTPUT_DIR.exists():
        print("\nGenerated files:")
        for f in sorted(OUTPUT_DIR.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                print(f"  - {f.name} ({size:,} bytes)")

    if video_path:
        print(f"\nFinal video: {video_path}")
        print("\nTo view the video:")
        print(f"  1. Copy from container: docker cp <container>:{video_path} ./output.mp4")
        print("  2. Or open in VSCode file explorer")


if __name__ == "__main__":
    asyncio.run(main())
