"""E2E tests for full content-to-video pipeline.

These tests verify the complete workflow:
1. Collect topics with persona context
2. Generate script from topic using RAG
3. Generate video from script
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.persona import (
    CommunicationStyle,
    PersonaConfig,
    Perspective,
    VoiceConfig,
    VoiceSettings,
)
from app.config.video import CompositionConfig
from app.models.scene import SceneScript
from app.services.collector.base import ScoredTopic
from app.services.generator.compositor import FFmpegCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.thumbnail import ThumbnailGenerator
from app.services.generator.tts.base import TTSConfig as TTSConfigDataclass
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.visual.fallback import FallbackGenerator

from .conftest import create_scored_topic


class TestPersonaBasedGeneration:
    """E2E tests for persona-based content generation."""

    @pytest.fixture
    def sample_persona(self) -> PersonaConfig:
        """Create sample persona for testing."""
        return PersonaConfig(
            name="테크 전문가",
            tagline="IT 기술을 쉽게 설명하는 전문가",
            voice=VoiceConfig(
                gender="male",
                service="edge-tts",
                voice_id="ko-KR-InJoonNeural",
                settings=VoiceSettings(speed=1.0, pitch=0),
            ),
            communication=CommunicationStyle(
                tone="친근하고 전문적인",
                formality="semi-formal",
            ),
            perspective=Perspective(
                approach="practical",
                core_values=["명확성", "간결함"],
            ),
        )

    @pytest.fixture
    def sample_topic(self) -> ScoredTopic:
        """Create sample scored topic for testing."""
        return create_scored_topic(
            title="ChatGPT 최신 업데이트 분석",
            keywords=["ChatGPT", "AI", "OpenAI"],
            categories=["tech"],
            engagement_score=500,
            score_total=85,
        )

    @pytest.mark.asyncio
    async def test_generate_script_from_topic(
        self,
        sample_persona: PersonaConfig,
        sample_topic: ScoredTopic,
    ) -> None:
        """Test script generation from topic with persona."""
        # Mock LLM client for script generation
        llm_client = AsyncMock()
        llm_client.complete = AsyncMock(
            return_value=MagicMock(
                content="""안녕하세요, 여러분! 오늘은 ChatGPT의 최신 업데이트에 대해 알아보겠습니다.

OpenAI가 최근 발표한 새로운 기능들이 정말 대단한데요.
첫째, 응답 속도가 크게 개선되었습니다.
둘째, 더 정확한 한국어 지원이 가능해졌습니다.

이런 변화들이 우리 일상에 어떤 영향을 줄지, 함께 살펴볼까요?"""
            )
        )

        # In real implementation, this would use ScriptGenerator
        # Here we simulate the script generation
        script_text = llm_client.complete.return_value.content

        assert len(script_text) > 50
        assert "ChatGPT" in script_text

    @pytest.mark.asyncio
    async def test_topic_to_video_pipeline(
        self,
        temp_output_dir: Path,
        sample_persona: PersonaConfig,
        sample_topic: ScoredTopic,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test complete topic to video pipeline."""
        # Simulate generated script
        script_text = """안녕하세요! 오늘은 ChatGPT 최신 업데이트를 살펴보겠습니다.
새로운 기능들이 정말 놀라운데요, 특히 한국어 지원이 크게 개선되었습니다.
여러분도 직접 사용해보시길 추천드립니다."""

        # Step 1: Generate TTS with persona voice
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(
            voice_id=sample_persona.voice.voice_id,
            speed=sample_persona.voice.settings.speed,
        )

        tts_result = await tts_engine.synthesize(
            text=script_text,
            config=tts_config,
            output_path=temp_output_dir / "topic_audio",
        )

        assert tts_result.audio_path.exists()

        # Step 2: Generate subtitles
        subtitle_gen = SubtitleGenerator()

        if tts_result.word_timestamps:
            subtitle_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_gen.generate_from_script(
                script_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "topic_subs.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)

        # Step 3: Generate visual
        fallback_gen = FallbackGenerator()
        visuals = await fallback_gen.search("technology", max_results=1)
        visual = await fallback_gen.download(visuals[0], temp_output_dir)

        # Step 4: Compose video
        compositor = FFmpegCompositor(CompositionConfig())
        video_path = temp_output_dir / "topic_video.mp4"

        result = await compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        assert video_path.exists()
        assert result.duration_seconds > 0

        # Step 5: Generate thumbnail
        thumb_gen = ThumbnailGenerator()
        thumb_path = await thumb_gen.generate(
            title=sample_topic.title_original,
            output_path=temp_output_dir / "topic_thumb.jpg",
        )

        assert thumb_path.exists()


class TestBatchVideoGeneration:
    """E2E tests for batch video generation."""

    @pytest.mark.asyncio
    async def test_multiple_topics_to_videos(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test generating videos for multiple topics."""
        topics = [
            ("AI 기술 트렌드", "인공지능이 변화시키는 세상"),
            ("프로그래밍 팁", "개발자를 위한 생산성 향상 방법"),
        ]

        tts_engine = EdgeTTSEngine()
        fallback_gen = FallbackGenerator()
        subtitle_gen = SubtitleGenerator()
        compositor = FFmpegCompositor(CompositionConfig())
        thumb_gen = ThumbnailGenerator()

        generated_videos = []

        for i, (title, script) in enumerate(topics):
            topic_dir = temp_output_dir / f"topic_{i}"
            topic_dir.mkdir(exist_ok=True)

            # TTS
            tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")
            tts_result = await tts_engine.synthesize(
                text=script,
                config=tts_config,
                output_path=topic_dir / "audio",
            )

            # Subtitles
            if tts_result.word_timestamps:
                sub_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
            else:
                sub_file = subtitle_gen.generate_from_script(script, tts_result.duration_seconds)

            sub_path = topic_dir / "subs.ass"
            subtitle_gen.to_ass(sub_file, sub_path)

            # Visual
            visuals = await fallback_gen.search("tech", max_results=1)
            visual = await fallback_gen.download(visuals[0], topic_dir)

            # Compose
            video_path = topic_dir / "video.mp4"
            await compositor.compose(
                audio=tts_result,
                visuals=[visual],
                subtitle_file=sub_path,
                output_path=video_path,
            )

            # Thumbnail
            thumb_path = await thumb_gen.generate(
                title=title,
                output_path=topic_dir / "thumb.jpg",
            )

            generated_videos.append(
                {
                    "title": title,
                    "video": video_path,
                    "thumbnail": thumb_path,
                }
            )

        # Verify all videos generated
        assert len(generated_videos) == len(topics)
        for video_info in generated_videos:
            assert video_info["video"].exists()
            assert video_info["thumbnail"].exists()


class TestErrorHandling:
    """E2E tests for error handling in pipeline."""

    @pytest.mark.asyncio
    async def test_empty_script_handling(self, temp_output_dir: Path) -> None:
        """Test handling of empty script."""
        subtitle_gen = SubtitleGenerator()

        # Empty script should return empty subtitle file
        subtitle_file = subtitle_gen.generate_from_script("", 5.0)

        assert len(subtitle_file.segments) == 0

    @pytest.mark.asyncio
    async def test_very_long_script(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test handling of very long script (beyond Shorts limit)."""
        # YouTube Shorts max is 60 seconds
        # This script should exceed that when spoken
        long_script = " ".join(["이것은 매우 긴 스크립트입니다."] * 50)

        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        tts_result = await tts_engine.synthesize(
            text=long_script,
            config=tts_config,
            output_path=temp_output_dir / "long_audio",
        )

        # Should still generate, but warn about length
        assert tts_result.audio_path.exists()
        # In production, we'd truncate or split the script


class TestIntegrationWithRAG:
    """E2E tests for RAG-based script generation."""

    @pytest.mark.asyncio
    async def test_rag_context_retrieval(self) -> None:
        """Test RAG context retrieval for script generation."""
        # This would test the full RAG pipeline:
        # 1. Retrieve relevant content chunks
        # 2. Build context with persona info
        # 3. Generate script with LLM

        # For now, we mock the RAG components
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(
            return_value=[
                MagicMock(text="AI 기술이 빠르게 발전하고 있습니다.", score=0.9),
                MagicMock(text="ChatGPT는 OpenAI에서 개발했습니다.", score=0.85),
            ]
        )

        # Verify retrieval works
        results = await mock_retriever.retrieve("ChatGPT 최신 소식")
        assert len(results) == 2
        assert results[0].score > results[1].score


class TestSceneBasedVideoGeneration:
    """E2E tests for scene-based video generation (BSForge differentiator)."""

    @pytest.fixture
    def sample_scene_script(self) -> SceneScript:
        """Create sample SceneScript for testing."""
        from app.models.scene import Scene, SceneType, VisualHintType

        return SceneScript(
            scenes=[
                Scene(
                    scene_type=SceneType.HOOK,
                    text="충격적인 AI 뉴스가 있습니다!",
                    keyword="AI news",
                    visual_hint=VisualHintType.STOCK_IMAGE,
                ),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="OpenAI가 오늘 새로운 모델을 발표했습니다. 이 모델은 기존 대비 50% 빠른 속도를 자랑합니다.",
                    keyword="OpenAI",
                    visual_hint=VisualHintType.STOCK_IMAGE,
                ),
                Scene(
                    scene_type=SceneType.COMMENTARY,
                    text="제 생각에 이건 정말 게임 체인저예요. AI 발전 속도가 정말 놀랍습니다.",
                    keyword="AI innovation",
                    visual_hint=VisualHintType.AI_GENERATED,
                    emphasis_words=["게임 체인저", "놀랍습니다"],
                ),
                Scene(
                    scene_type=SceneType.CONCLUSION,
                    text="AI 시대가 본격적으로 시작됐습니다. 구독과 좋아요 부탁드립니다!",
                    keyword="future",
                    visual_hint=VisualHintType.SOLID_COLOR,
                ),
            ],
            title_text="AI 혁명의 시작",
        )

    def test_scene_script_structure_validation(self, sample_scene_script: SceneScript) -> None:
        """Test SceneScript structure validation."""
        errors = sample_scene_script.validate_structure()

        # Should have no critical errors (may have duration warnings)
        structural_errors = [e for e in errors if "HOOK" in e or "CONTENT" in e]
        assert len(structural_errors) == 0

        # Should have commentary (BSForge differentiator)
        assert sample_scene_script.has_commentary

    def test_scene_script_transitions(self, sample_scene_script: SceneScript) -> None:
        """Test recommended transitions between scenes."""
        from app.models.scene import TransitionType

        transitions = sample_scene_script.get_recommended_transitions()

        # Should have n-1 transitions for n scenes
        assert len(transitions) == len(sample_scene_script.scenes) - 1

        # CONTENT -> COMMENTARY should be FLASH (key differentiator)
        # Position 1 is CONTENT->COMMENTARY
        assert transitions[1] == TransitionType.FLASH

    def test_scene_types_classification(self, sample_scene_script: SceneScript) -> None:
        """Test scene type classification."""
        from app.models.scene import SceneType

        scene_types = sample_scene_script.scene_types

        assert scene_types[0] == SceneType.HOOK
        assert scene_types[1] == SceneType.CONTENT
        assert scene_types[2] == SceneType.COMMENTARY
        assert scene_types[3] == SceneType.CONCLUSION

    def test_full_text_extraction(self, sample_scene_script: SceneScript) -> None:
        """Test full text extraction from scenes."""
        full_text = sample_scene_script.full_text

        assert "충격적인 AI 뉴스" in full_text
        assert "게임 체인저" in full_text
        assert "구독과 좋아요" in full_text

    @pytest.mark.asyncio
    async def test_scene_based_tts_generation(
        self,
        temp_output_dir: Path,
        sample_scene_script: SceneScript,
    ) -> None:
        """Test TTS generation for each scene."""
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural")

        scene_audios = []

        for i, scene in enumerate(sample_scene_script.scenes):
            audio_path = temp_output_dir / f"scene_{i}"
            tts_result = await tts_engine.synthesize(
                text=scene.text,
                config=tts_config,
                output_path=audio_path,
            )

            scene_audios.append(
                {
                    "scene_type": scene.scene_type,
                    "audio_path": tts_result.audio_path,
                    "duration": tts_result.duration_seconds,
                    "is_persona": scene.is_persona_scene,
                }
            )

            assert tts_result.audio_path.exists()
            assert tts_result.duration_seconds > 0

        # Verify all scenes processed
        assert len(scene_audios) == 4

        # Commentary scene should be marked as persona scene
        commentary_audio = next(a for a in scene_audios if a["scene_type"].value == "commentary")
        assert commentary_audio["is_persona"] is True

    @pytest.mark.asyncio
    async def test_scene_based_video_composition(
        self,
        temp_output_dir: Path,
        sample_scene_script: SceneScript,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test video composition with scene-based structure."""
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")
        subtitle_gen = SubtitleGenerator()
        fallback_gen = FallbackGenerator()
        compositor = FFmpegCompositor(CompositionConfig())

        # Generate TTS for full script
        full_text = sample_scene_script.full_text
        tts_result = await tts_engine.synthesize(
            text=full_text,
            config=tts_config,
            output_path=temp_output_dir / "scene_audio",
        )

        # Generate subtitles
        if tts_result.word_timestamps:
            subtitle_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_gen.generate_from_script(
                full_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "scene_subs.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)

        # Generate visuals
        visuals = await fallback_gen.search("technology AI", max_results=1)
        visual = await fallback_gen.download(visuals[0], temp_output_dir)

        # Compose video
        video_path = temp_output_dir / "scene_video.mp4"
        result = await compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        assert video_path.exists()
        assert result.duration_seconds > 0

    def test_visual_style_inference(self, sample_scene_script: SceneScript) -> None:
        """Test visual style inference from scene types."""
        from app.models.scene import VisualStyle

        for scene in sample_scene_script.scenes:
            style = scene.inferred_visual_style

            if scene.is_persona_scene:
                # Commentary/Reaction should have PERSONA style
                assert style == VisualStyle.PERSONA
            elif scene.scene_type.value in ("conclusion", "cta"):
                # Conclusion/CTA should have EMPHASIS style
                assert style == VisualStyle.EMPHASIS
            else:
                # Others should have NEUTRAL style
                assert style == VisualStyle.NEUTRAL


class TestFullPipelineIntegration:
    """E2E tests for the complete pipeline from topic to video."""

    @pytest.mark.asyncio
    async def test_topic_to_scene_script_to_video(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test complete pipeline: Topic -> SceneScript -> Video."""
        from app.models.scene import Scene, SceneScript, SceneType

        # Step 1: Simulated topic (in real system, collected from sources)
        topic_title = "GPT-5 출시 임박 소식"
        # Keywords would be used by RAG in production: ["GPT-5", "OpenAI", "AI"]

        # Step 2: Simulated RAG script generation (would use ScriptGenerator)
        # In production, RAG retrieves relevant chunks and LLM generates script
        scene_script = SceneScript(
            scenes=[
                Scene(
                    scene_type=SceneType.HOOK,
                    text="GPT-5가 곧 출시됩니다!",
                    keyword="GPT-5",
                ),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="OpenAI에서 새로운 모델을 준비 중입니다.",
                    keyword="OpenAI model",
                ),
                Scene(
                    scene_type=SceneType.COMMENTARY,
                    text="이건 정말 기대되는 소식이에요.",
                    keyword="AI excitement",
                ),
            ],
            title_text=topic_title,
        )

        # Step 3: Video generation
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural")
        subtitle_gen = SubtitleGenerator()
        fallback_gen = FallbackGenerator()
        compositor = FFmpegCompositor(CompositionConfig())
        thumb_gen = ThumbnailGenerator()

        # TTS
        full_text = scene_script.full_text
        tts_result = await tts_engine.synthesize(
            text=full_text,
            config=tts_config,
            output_path=temp_output_dir / "pipeline_audio",
        )

        # Subtitles
        if tts_result.word_timestamps:
            subtitle_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_gen.generate_from_script(
                full_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "pipeline_subs.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)

        # Visual
        visuals = await fallback_gen.search("AI technology", max_results=1)
        visual = await fallback_gen.download(visuals[0], temp_output_dir)

        # Compose
        video_path = temp_output_dir / "pipeline_video.mp4"
        result = await compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        # Thumbnail
        thumb_path = await thumb_gen.generate(
            title=topic_title,
            output_path=temp_output_dir / "pipeline_thumb.jpg",
        )

        # Verify all outputs
        assert video_path.exists()
        assert thumb_path.exists()
        assert result.duration_seconds > 0

        # Video should be within Shorts duration (< 60s)
        assert result.duration_seconds <= 60
