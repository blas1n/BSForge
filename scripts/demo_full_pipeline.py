#!/usr/bin/env python
"""Full pipeline demo: Topic Collection → Script → Video Generation.

This script demonstrates the complete BSForge pipeline:
1. Collect topics from sources (mocked for demo)
2. Normalize, filter, and score topics
3. Generate script from top topic
4. Generate video with TTS, subtitles, and visuals

Run with: uv run python scripts/demo_full_pipeline.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if TYPE_CHECKING:
    from app.services.collector.base import ScoredTopic


async def demo_topic_collection() -> dict:
    """Demo topic collection pipeline."""
    print("\n" + "=" * 60)
    print("PHASE 1: Topic Collection")
    print("=" * 60)

    from app.config import DedupConfig, ScoringConfig
    from app.config.filtering import (
        CategoryFilter,
        ExcludeFilters,
        IncludeFilters,
        KeywordFilter,
        TopicFilterConfig,
    )
    from app.services.collector.base import RawTopic
    from app.services.collector.deduplicator import TopicDeduplicator
    from app.services.collector.filter import TopicFilter
    from app.services.collector.normalizer import TopicNormalizer
    from app.services.collector.scorer import TopicScorer

    # 1. Simulate raw topics from various sources
    print("\n[1/4] Collecting raw topics from sources...")

    raw_topics = [
        RawTopic(
            source_id="hackernews",
            source_url="https://news.ycombinator.com/item?id=12345",  # type: ignore
            title="Claude 3.5 Sonnet Achieves New Benchmarks in Coding Tasks",
            content="Anthropic's latest model shows remarkable improvements...",
            published_at=datetime.now(UTC),
            metrics={"score": 850, "comments": 234},
        ),
        RawTopic(
            source_id="reddit_tech",
            source_url="https://reddit.com/r/technology/comments/abc123",  # type: ignore
            title="OpenAI GPT-5 Leaked: What We Know So Far",
            content="Rumors suggest GPT-5 will feature...",
            published_at=datetime.now(UTC),
            metrics={"upvotes": 5200, "comments": 890},
        ),
        RawTopic(
            source_id="google_trends",
            source_url="https://trends.google.com/trends/trendingsearches",  # type: ignore
            title="AI 규제 법안 국회 통과",
            content="인공지능 관련 규제 법안이 오늘 국회를 통과했습니다...",
            published_at=datetime.now(UTC),
            metrics={"search_volume": 50000},
        ),
        RawTopic(
            source_id="youtube_trending",
            source_url="https://youtube.com/watch?v=xyz789",  # type: ignore
            title="이 AI 도구 하나면 영상 제작 끝! (무료)",
            content="영상 제작을 자동화하는 AI 도구를 소개합니다...",
            published_at=datetime.now(UTC),
            metrics={"views": 120000, "likes": 8500},
        ),
    ]

    print(f"   Collected {len(raw_topics)} raw topics:")
    for t in raw_topics:
        print(f"   - [{t.source_id}] {t.title[:50]}...")

    # 2. Normalize topics (mock LLM for demo)
    print("\n[2/4] Normalizing topics (translation, classification)...")

    # Create enough mock responses for all LLM calls (translation + classification per topic)
    llm_client = AsyncMock()
    llm_responses = [
        # Topic 1: Claude (translation)
        MagicMock(content="Claude 3.5 Sonnet이 코딩 작업에서 새로운 벤치마크 달성"),
        # Topic 1: Claude (classification)
        MagicMock(
            content='{"categories": ["tech", "ai"], "keywords": ["claude", "anthropic", "coding", "benchmark"], "entities": {"organizations": ["Anthropic"]}, "summary": "Claude 3.5 Sonnet achieves new coding benchmarks"}'
        ),
        # Topic 2: GPT-5 (translation)
        MagicMock(content="OpenAI GPT-5 유출: 지금까지 알려진 것들"),
        # Topic 2: GPT-5 (classification)
        MagicMock(
            content='{"categories": ["tech", "ai"], "keywords": ["openai", "gpt-5", "leak"], "entities": {"organizations": ["OpenAI"]}, "summary": "GPT-5 leak rumors and speculation"}'
        ),
        # Topic 3: AI 규제 (no translation needed, classification only)
        MagicMock(
            content='{"categories": ["tech", "politics"], "keywords": ["ai", "regulation", "korea", "law"], "entities": {"locations": ["Korea"]}, "summary": "AI regulation bill passes Korean parliament"}'
        ),
        # Topic 4: AI 도구 (no translation needed, classification only)
        MagicMock(
            content='{"categories": ["tech", "content"], "keywords": ["ai", "video", "automation", "free"], "entities": {}, "summary": "Free AI tool for video production automation"}'
        ),
    ]
    llm_client.complete = AsyncMock(side_effect=llm_responses)

    normalizer = TopicNormalizer(llm_client=llm_client)
    normalized = []

    for topic in raw_topics:
        source_uuid = uuid.uuid4()
        result = await normalizer.normalize(topic, source_uuid)
        normalized.append(result)
        print(f"   - {result.title_normalized[:40]}... → categories: {result.categories}")

    # 3. Filter topics
    print("\n[3/4] Filtering topics (tech category only)...")

    filter_config = TopicFilterConfig(
        include=IncludeFilters(
            categories=[
                CategoryFilter(name="tech"),
                CategoryFilter(name="ai"),
            ],
            keywords=[
                KeywordFilter(keyword="ai"),
                KeywordFilter(keyword="claude"),
                KeywordFilter(keyword="gpt"),
                KeywordFilter(keyword="영상"),
            ],
        ),
        exclude=ExcludeFilters(
            keywords=["politics", "regulation", "법안"],
        ),
        require_category_match=True,
    )
    topic_filter = TopicFilter(filter_config)

    filtered = []
    for topic in normalized:
        result = topic_filter.filter(topic)
        if result.passed:
            filtered.append(topic)
            print(f"   PASS: {topic.title_normalized[:50]}...")
        else:
            print(f"   FAIL: {topic.title_normalized[:50]}... (reason: {result.reason})")

    # 4. Deduplicate (mock Redis)
    print("\n[4/4] Deduplicating topics...")

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    deduplicator = TopicDeduplicator(redis=redis_mock, config=DedupConfig())

    unique = []
    for topic in filtered:
        result = await deduplicator.is_duplicate(topic, "demo_channel")
        if not result.is_duplicate:
            unique.append(topic)
            await deduplicator.mark_as_seen(topic, "demo_channel")
            print(f"   UNIQUE: {topic.title_normalized[:50]}...")
        else:
            print(f"   DUPLICATE: {topic.title_normalized[:50]}...")

    # 5. Score topics
    print("\n[5/4] Scoring topics...")

    scorer = TopicScorer(config=ScoringConfig())
    scored = [scorer.score(t) for t in unique]

    # Sort by score
    scored.sort(key=lambda x: x.score_total, reverse=True)

    print("\n   Final ranked topics:")
    for i, topic in enumerate(scored, 1):
        print(f"   {i}. [Score: {topic.score_total}] {topic.title_normalized[:45]}...")

    if scored:
        top_topic = scored[0]
        print(f"\n   Selected topic: {top_topic.title_normalized}")
        return {
            "topic": top_topic,
            "all_scored": scored,
        }

    return {"topic": None, "all_scored": []}


async def demo_script_generation(topic: ScoredTopic) -> str:
    """Demo script generation from topic."""
    print("\n" + "=" * 60)
    print("PHASE 2: Script Generation")
    print("=" * 60)

    # In production, this would use the RAG system with persona
    # For demo, we'll generate a mock script

    print(f"\n[1/2] Analyzing topic: {topic.title_normalized}")
    print(f"   Keywords: {topic.keywords}")
    print(f"   Categories: {topic.categories}")

    print("\n[2/2] Generating script with persona voice...")

    # Demo script based on topic
    if "claude" in topic.title_normalized.lower():
        script = """안녕하세요 여러분! 오늘은 정말 흥미로운 AI 소식을 가져왔습니다.

Anthropic의 Claude 3.5 Sonnet이 코딩 벤치마크에서 새로운 기록을 세웠다고 합니다!

기존 모델들과 비교했을 때 코드 생성 능력이 크게 향상되었는데요,
특히 복잡한 알고리즘 문제 해결에서 뛰어난 성능을 보여줬습니다.

AI 개발자들 사이에서는 벌써 뜨거운 반응이 나오고 있어요.
여러분도 한번 사용해보시는 건 어떨까요?

다음 영상에서 더 자세한 내용을 다뤄볼게요. 구독과 좋아요 부탁드립니다!"""

    elif "gpt" in topic.title_normalized.lower():
        script = """여러분, GPT-5에 대한 새로운 소문이 돌고 있습니다!

아직 공식 발표는 없지만, 여러 소스에서 흥미로운 정보가 나오고 있는데요.

멀티모달 성능이 크게 향상될 것이라는 예측과 함께,
추론 능력도 한층 업그레이드될 것으로 보입니다.

물론 루머이기 때문에 확정된 건 아니지만,
OpenAI의 다음 행보가 정말 기대되지 않나요?

새로운 소식이 나오면 바로 전해드릴게요!"""

    else:
        script = """안녕하세요! 오늘도 흥미로운 AI 소식을 가져왔습니다.

요즘 AI 기술이 정말 빠르게 발전하고 있죠.
특히 영상 제작 분야에서 혁신적인 변화가 일어나고 있는데요.

이제는 AI 도구 하나로 기획부터 편집까지 자동화할 수 있게 되었습니다.
직접 사용해본 결과, 정말 놀라운 효율성을 보여줬어요.

앞으로 더 많은 AI 도구들을 리뷰해드릴 예정이니
구독과 알림 설정 잊지 마세요!"""

    print("\n   Generated Script:")
    print("   " + "-" * 50)
    for line in script.split("\n"):
        if line.strip():
            print(f"   {line}")
    print("   " + "-" * 50)
    print(f"\n   Script length: {len(script)} characters")

    return script


async def demo_video_generation(
    script: str,
    topic_title: str,
    topic_keywords: list[str] | None = None,
    template_name: str = "korean_viral",
) -> Path | None:
    """Demo video generation from script.

    Args:
        script: Script text
        topic_title: Topic title for thumbnail
        topic_keywords: Keywords for image search
        template_name: Video template name (e.g., "korean_viral", "minimal")
    """
    print("\n" + "=" * 60)
    print("PHASE 3: Video Generation")
    print("=" * 60)

    from app.config.video import CompositionConfig
    from app.core.template_loader import load_template
    from app.services.generator.compositor import FFmpegCompositor
    from app.services.generator.subtitle import SubtitleGenerator
    from app.services.generator.thumbnail import ThumbnailGenerator
    from app.services.generator.tts.base import TTSConfig
    from app.services.generator.tts.edge import EdgeTTSEngine
    from app.services.generator.visual.base import VisualAsset
    from app.services.generator.visual.fallback import FallbackGenerator
    from app.services.generator.visual.pexels import PexelsClient

    # Load video template
    print(f"\n[0/6] Loading video template: {template_name}")
    try:
        template = load_template(template_name)
        print(f"   Template: {template.name}")
        print(f"   Description: {template.description}")
        if template.layout.title_overlay and template.layout.title_overlay.enabled:
            print("   Title overlay: ENABLED")
        if template.visual_effects.ken_burns_enabled:
            print("   Ken Burns effect: ENABLED")
        if template.visual_effects.color_grading_enabled:
            print("   Color grading: ENABLED")
    except Exception as e:
        print(f"   Warning: Failed to load template '{template_name}': {e}")
        print("   Using default settings")
        template = None

    output_dir = Path("/tmp/bsforge_full_demo")
    output_dir.mkdir(exist_ok=True)

    # 1. TTS Generation
    print("\n[1/5] Generating TTS audio...")
    tts_engine = EdgeTTSEngine()
    tts_config = TTSConfig(voice_id="ko-KR-InJoonNeural", speed=1.0)

    tts_result = await tts_engine.synthesize(
        text=script,
        config=tts_config,
        output_path=output_dir / "script_audio",
    )
    print(f"   Audio: {tts_result.audio_path}")
    print(f"   Duration: {tts_result.duration_seconds:.1f} seconds")
    print(f"   Word timestamps: {len(tts_result.word_timestamps or [])} words")

    # 2. Subtitle Generation
    print("\n[2/5] Generating subtitles...")
    subtitle_gen = SubtitleGenerator()

    if tts_result.word_timestamps:
        subtitle_file = subtitle_gen.generate_from_timestamps(
            tts_result.word_timestamps,
            template=template,
        )
    else:
        subtitle_file = subtitle_gen.generate_from_script(script, tts_result.duration_seconds)

    subtitle_path = output_dir / "script_subtitles.ass"
    subtitle_gen.to_ass(subtitle_file, subtitle_path, template=template)
    print(f"   Subtitles: {subtitle_path}")
    print(f"   Segments: {len(subtitle_file.segments)}")

    # 3. Visual Generation - Use Pexels for multiple stock images (양산형 스타일)
    print("\n[3/5] Fetching background images from Pexels...")

    # 양산형 스타일: 여러 이미지로 장면 전환 (2-3초마다) - 빠른 컷
    num_images = max(5, int(tts_result.duration_seconds / 2.5))  # 2.5초당 1개 이미지
    print(f"   Fetching {num_images} images for {tts_result.duration_seconds:.1f}s video...")

    downloaded_assets: list[VisualAsset] = []
    try:
        pexels = PexelsClient()

        # AI/테크 관련 이미지 검색 - 내용과 관련된 범용 검색어 사용
        # 토픽 키워드가 너무 구체적이면 관련 없는 이미지가 나오므로 범용 테크 키워드 사용
        search_queries = [
            "artificial intelligence robot",  # AI 관련
            "coding programming laptop",  # 코딩 관련
            "technology futuristic",  # 테크 관련
            "computer screen data",  # 컴퓨터 관련
            "digital network abstract",  # 디지털 관련
        ]

        for query in search_queries:
            if len(downloaded_assets) >= num_images:
                break

            remaining = num_images - len(downloaded_assets)
            print(f"   Searching: '{query}' (need {remaining} more)")

            assets = await pexels.search_images(query, max_results=remaining)
            for asset in assets:
                if len(downloaded_assets) >= num_images:
                    break
                try:
                    downloaded = await pexels.download(asset, output_dir)
                    # 각 이미지의 재생 시간 설정 (2-3초 빠른 컷)
                    downloaded.duration = min(3.0, tts_result.duration_seconds / num_images)
                    downloaded_assets.append(downloaded)
                    print(
                        f"   Downloaded: {downloaded.path.name} ({downloaded.metadata.get('photographer', 'Unknown')})"
                    )
                except Exception as e:
                    print(f"   Download failed: {e}")

        await pexels.close()
    except Exception as e:
        print(f"   Pexels failed: {e}")

    # Fallback to solid color if not enough images
    if len(downloaded_assets) < 1:
        print("   Falling back to solid color background...")
        fallback_gen = FallbackGenerator()
        fallback_assets = await fallback_gen.search("fallback", max_results=1)
        if fallback_assets:
            downloaded = await fallback_gen.download(fallback_assets[0], output_dir)
            downloaded.duration = tts_result.duration_seconds
            downloaded_assets.append(downloaded)
            print(f"   Background: {downloaded.path} (fallback)")

    if not downloaded_assets:
        print("   ERROR: Failed to generate any visuals")
        return None

    print(f"   Total images: {len(downloaded_assets)}")

    # 4. Thumbnail Generation
    print("\n[4/5] Generating thumbnail...")
    thumb_gen = ThumbnailGenerator()
    thumb_path = output_dir / "thumbnail.jpg"

    # Create short title for thumbnail
    thumb_title = topic_title[:30] + "..." if len(topic_title) > 30 else topic_title
    await thumb_gen.generate(title=thumb_title, output_path=thumb_path)
    print(f"   Thumbnail: {thumb_path}")

    # 5. Video Composition (양산형 스타일: Ken Burns 효과 + 장면 전환 + BGM)
    print("\n[5/5] Composing final video with FFmpeg...")
    print(f"   Using {len(downloaded_assets)} images with Ken Burns zoom effect...")

    # BGM 설정
    bgm_path = Path("/workspace/assets/bgm/tech_vibe.mp3")
    if bgm_path.exists():
        print(f"   Adding background music: {bgm_path.name}")
    else:
        print("   No BGM found, proceeding without background music")
        bgm_path = None

    compositor = FFmpegCompositor(CompositionConfig(), template=template)

    # Prepare title text for overlay (from topic title)
    title_text = (
        topic_title[:50]
        if template and template.layout.title_overlay and template.layout.title_overlay.enabled
        else None
    )
    if title_text:
        print(f"   Adding title overlay: {title_text[:30]}...")

    final_path = output_dir / "final_shorts.mp4"
    await compositor.compose(
        audio=tts_result,
        visuals=downloaded_assets,  # 여러 이미지 전달
        subtitle_file=subtitle_path,
        output_path=final_path,
        background_music_path=bgm_path,  # BGM 추가
        title_text=title_text,  # 상단 제목 오버레이
    )

    if final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print("\n   VIDEO GENERATED SUCCESSFULLY!")
        print(f"   Output: {final_path}")
        print(f"   Size: {size_mb:.2f} MB")
        print(f"   Duration: {tts_result.duration_seconds:.1f} seconds")
        return final_path

    return None


async def main() -> None:
    """Run full pipeline demo."""
    print("=" * 60)
    print("BSForge Full Pipeline Demo")
    print("Topic Collection → Script Generation → Video Production")
    print("=" * 60)

    # Check FFmpeg
    if not shutil.which("ffmpeg"):
        print("\nERROR: FFmpeg is required for video generation.")
        print("Please install FFmpeg or use DevContainer.")
        return

    # Phase 1: Topic Collection
    result = await demo_topic_collection()

    if not result["topic"]:
        print("\nNo topics passed filtering. Demo ended.")
        return

    topic = result["topic"]

    # Phase 2: Script Generation
    script = await demo_script_generation(topic)

    # Phase 3: Video Generation (pass topic keywords for image search)
    # Use Korean title for overlay (title_translated if available, else title_normalized)
    title_for_overlay = topic.title_translated or topic.title_normalized
    video_path = await demo_video_generation(script, title_for_overlay, topic.keywords)

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    output_dir = Path("/tmp/bsforge_full_demo")
    if output_dir.exists():
        print("\nGenerated files:")
        for f in sorted(output_dir.iterdir()):
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
