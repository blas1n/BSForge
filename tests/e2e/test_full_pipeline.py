"""E2E tests for full content-to-video pipeline.

These tests verify the complete workflow:
1. Collect topics with persona context
2. Generate script from topic
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
from app.models.scene import Scene, SceneScript, SceneType, TransitionType, VisualStyle
from app.services.collector.base import ScoredTopic
from app.services.generator.ffmpeg import FFmpegWrapper
from app.services.generator.remotion_compositor import RemotionCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.tts.base import TTSSynthesisConfig as TTSConfigDataclass
from app.services.generator.tts.edge import EdgeTTSEngine

from .conftest import create_fallback_visual, create_scored_topic


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
                core_values=["명확성", "간결함"],
            ),
        )

    @pytest.fixture
    def sample_topic(self) -> ScoredTopic:
        """Create sample scored topic for testing."""
        return create_scored_topic(
            title="ChatGPT 최신 업데이트 분석",
            terms=["chatgpt", "ai", "openai", "tech"],
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
        ffmpeg_wrapper: FFmpegWrapper,
        edge_tts_engine: EdgeTTSEngine,
        remotion_compositor: RemotionCompositor,
        subtitle_generator: SubtitleGenerator,
    ) -> None:
        """Test complete topic to video pipeline."""
        script_text = """안녕하세요! 오늘은 ChatGPT 최신 업데이트를 살펴보겠습니다.
새로운 기능들이 정말 놀라운데요, 특히 한국어 지원이 크게 개선되었습니다.
여러분도 직접 사용해보시길 추천드립니다."""

        # Step 1: Generate TTS with persona voice
        tts_config = TTSConfigDataclass(
            voice_id=sample_persona.voice.voice_id,
            speed=sample_persona.voice.settings.speed,
        )

        tts_result = await edge_tts_engine.synthesize(
            text=script_text,
            config=tts_config,
            output_path=temp_output_dir / "topic_audio",
        )

        assert tts_result.audio_path.exists()

        # Step 2: Generate subtitles
        if tts_result.word_timestamps:
            subtitle_file = subtitle_generator.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_generator.generate_from_script(
                script_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "topic_subs.ass"
        subtitle_generator.to_ass(subtitle_file, subtitle_path)

        # Step 3: Generate visual (fallback solid color)
        visual = create_fallback_visual(temp_output_dir / "visuals")

        # Step 4: Compose video
        video_path = temp_output_dir / "topic_video.mp4"

        result = await remotion_compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        assert video_path.exists()
        assert result.duration_seconds > 0

        # Step 5: Extract thumbnail from first frame
        thumb_path = temp_output_dir / "topic_thumb.jpg"
        stream = ffmpeg_wrapper.extract_frame(
            video_path=video_path,
            output_path=thumb_path,
            seek_seconds=0.0,
            quality=2,
        )
        await ffmpeg_wrapper.run(stream)

        assert thumb_path.exists()


class TestBatchVideoGeneration:
    """E2E tests for batch video generation."""

    @pytest.mark.asyncio
    async def test_multiple_topics_to_videos(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
        ffmpeg_wrapper: FFmpegWrapper,
        edge_tts_engine: EdgeTTSEngine,
        remotion_compositor: RemotionCompositor,
        subtitle_generator: SubtitleGenerator,
    ) -> None:
        """Test generating videos for multiple topics."""
        topics = [
            ("AI 기술 트렌드", "인공지능이 변화시키는 세상"),
            ("프로그래밍 팁", "개발자를 위한 생산성 향상 방법"),
        ]

        generated_videos = []

        for i, (title, script) in enumerate(topics):
            topic_dir = temp_output_dir / f"topic_{i}"
            topic_dir.mkdir(exist_ok=True)

            # TTS
            tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")
            tts_result = await edge_tts_engine.synthesize(
                text=script,
                config=tts_config,
                output_path=topic_dir / "audio",
            )

            # Subtitles
            if tts_result.word_timestamps:
                sub_file = subtitle_generator.generate_from_timestamps(tts_result.word_timestamps)
            else:
                sub_file = subtitle_generator.generate_from_script(
                    script, tts_result.duration_seconds
                )

            sub_path = topic_dir / "subs.ass"
            subtitle_generator.to_ass(sub_file, sub_path)

            # Visual (fallback solid color)
            visual = create_fallback_visual(topic_dir / "visuals", name=f"bg_{i}")

            # Compose
            video_path = topic_dir / "video.mp4"
            await remotion_compositor.compose(
                audio=tts_result,
                visuals=[visual],
                subtitle_file=sub_path,
                output_path=video_path,
            )

            # Extract thumbnail from first frame
            thumb_path = topic_dir / "thumb.jpg"
            stream = ffmpeg_wrapper.extract_frame(
                video_path=video_path,
                output_path=thumb_path,
                seek_seconds=0.0,
                quality=2,
            )
            await ffmpeg_wrapper.run(stream)

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
    async def test_empty_script_handling(
        self,
        temp_output_dir: Path,
        subtitle_generator: SubtitleGenerator,
    ) -> None:
        """Test handling of empty script."""
        subtitle_file = subtitle_generator.generate_from_script("", 5.0)

        assert len(subtitle_file.segments) == 0

    @pytest.mark.asyncio
    async def test_very_long_script(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
        edge_tts_engine: EdgeTTSEngine,
    ) -> None:
        """Test handling of very long script (beyond Shorts limit)."""
        long_script = " ".join(["이것은 매우 긴 스크립트입니다."] * 50)

        tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        tts_result = await edge_tts_engine.synthesize(
            text=long_script,
            config=tts_config,
            output_path=temp_output_dir / "long_audio",
        )

        assert tts_result.audio_path.exists()


class TestSceneBasedVideoGeneration:
    """E2E tests for scene-based video generation (BSForge differentiator)."""

    @pytest.fixture
    def sample_scene_script(self) -> SceneScript:
        """Create sample SceneScript for testing."""
        return SceneScript(
            scenes=[
                Scene(
                    scene_type=SceneType.HOOK,
                    text="충격적인 AI 뉴스가 있습니다!",
                    visual_keyword="AI news announcement breaking",
                ),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text=(
                        "OpenAI가 오늘 새로운 모델을 발표했습니다. "
                        "이 모델은 기존 대비 50% 빠른 속도를 자랑합니다."
                    ),
                    visual_keyword="OpenAI technology innovation",
                ),
                Scene(
                    scene_type=SceneType.COMMENTARY,
                    text="제 생각에 이건 정말 게임 체인저예요. AI 발전 속도가 정말 놀랍습니다.",
                    visual_keyword="AI innovation breakthrough future",
                    emphasis_words=["게임 체인저", "놀랍습니다"],
                ),
                Scene(
                    scene_type=SceneType.CONCLUSION,
                    text="AI 시대가 본격적으로 시작됐습니다. 구독과 좋아요 부탁드립니다!",
                    visual_keyword="future technology digital era",
                ),
            ],
            headline="AI 혁명, 시작됐다",
        )

    def test_scene_script_structure_validation(self, sample_scene_script: SceneScript) -> None:
        """Test SceneScript structure validation."""
        errors = sample_scene_script.validate_structure()

        structural_errors = [e for e in errors if "HOOK" in e or "CONTENT" in e]
        assert len(structural_errors) == 0

        assert sample_scene_script.has_commentary

    def test_scene_script_transitions(self, sample_scene_script: SceneScript) -> None:
        """Test recommended transitions between scenes."""
        transitions = sample_scene_script.get_recommended_transitions()

        assert len(transitions) == len(sample_scene_script.scenes) - 1

        # CONTENT -> COMMENTARY should be FLASH (key differentiator)
        assert transitions[1] == TransitionType.FLASH

    def test_scene_types_classification(self, sample_scene_script: SceneScript) -> None:
        """Test scene type classification."""
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
        edge_tts_engine: EdgeTTSEngine,
    ) -> None:
        """Test TTS generation for each scene."""
        tts_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural")

        scene_audios = []

        for i, scene in enumerate(sample_scene_script.scenes):
            audio_path = temp_output_dir / f"scene_{i}"
            tts_result = await edge_tts_engine.synthesize(
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

        assert len(scene_audios) == 4

        commentary_audio = next(a for a in scene_audios if a["scene_type"].value == "commentary")
        assert commentary_audio["is_persona"] is True

    @pytest.mark.asyncio
    async def test_scene_based_video_composition(
        self,
        temp_output_dir: Path,
        sample_scene_script: SceneScript,
        skip_without_ffmpeg: None,
        edge_tts_engine: EdgeTTSEngine,
        remotion_compositor: RemotionCompositor,
        subtitle_generator: SubtitleGenerator,
    ) -> None:
        """Test video composition with scene-based structure."""
        tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        # Generate TTS for full script
        full_text = sample_scene_script.full_text
        tts_result = await edge_tts_engine.synthesize(
            text=full_text,
            config=tts_config,
            output_path=temp_output_dir / "scene_audio",
        )

        # Generate subtitles
        if tts_result.word_timestamps:
            subtitle_file = subtitle_generator.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_generator.generate_from_script(
                full_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "scene_subs.ass"
        subtitle_generator.to_ass(subtitle_file, subtitle_path)

        # Generate visual (fallback solid color)
        visual = create_fallback_visual(temp_output_dir / "visuals")

        # Compose video
        video_path = temp_output_dir / "scene_video.mp4"
        result = await remotion_compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        assert video_path.exists()
        assert result.duration_seconds > 0

    def test_visual_style_inference(self, sample_scene_script: SceneScript) -> None:
        """Test visual style inference from scene types."""
        for scene in sample_scene_script.scenes:
            style = scene.inferred_visual_style

            if scene.is_persona_scene:
                assert style == VisualStyle.PERSONA
            elif scene.scene_type.value in ("conclusion", "cta"):
                assert style == VisualStyle.EMPHASIS
            else:
                assert style == VisualStyle.NEUTRAL


class TestFullPipelineIntegration:
    """E2E tests for the complete pipeline from topic to video."""

    @pytest.mark.asyncio
    async def test_topic_to_scene_script_to_video(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
        ffmpeg_wrapper: FFmpegWrapper,
        edge_tts_engine: EdgeTTSEngine,
        remotion_compositor: RemotionCompositor,
        subtitle_generator: SubtitleGenerator,
    ) -> None:
        """Test complete pipeline: Topic -> SceneScript -> Video."""
        scene_script = SceneScript(
            scenes=[
                Scene(
                    scene_type=SceneType.HOOK,
                    text="GPT-5가 곧 출시됩니다!",
                    visual_keyword="GPT-5 AI announcement breaking news",
                ),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="OpenAI에서 새로운 모델을 준비 중입니다.",
                    visual_keyword="OpenAI model technology innovation",
                ),
                Scene(
                    scene_type=SceneType.COMMENTARY,
                    text="이건 정말 기대되는 소식이에요.",
                    visual_keyword="AI excitement future technology",
                ),
            ],
            headline="GPT-5, 곧 출시",
        )

        # Video generation
        tts_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural")

        # TTS
        full_text = scene_script.full_text
        tts_result = await edge_tts_engine.synthesize(
            text=full_text,
            config=tts_config,
            output_path=temp_output_dir / "pipeline_audio",
        )

        # Subtitles
        if tts_result.word_timestamps:
            subtitle_file = subtitle_generator.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_generator.generate_from_script(
                full_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "pipeline_subs.ass"
        subtitle_generator.to_ass(subtitle_file, subtitle_path)

        # Visual (fallback solid color)
        visual = create_fallback_visual(temp_output_dir / "visuals")

        # Compose
        video_path = temp_output_dir / "pipeline_video.mp4"
        result = await remotion_compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=subtitle_path,
            output_path=video_path,
        )

        # Extract thumbnail from first frame
        thumb_path = temp_output_dir / "pipeline_thumb.jpg"
        stream = ffmpeg_wrapper.extract_frame(
            video_path=video_path,
            output_path=thumb_path,
            seek_seconds=0.0,
            quality=2,
        )
        await ffmpeg_wrapper.run(stream)

        # Verify all outputs
        assert video_path.exists()
        assert thumb_path.exists()
        assert result.duration_seconds > 0

        # Video should be within Shorts duration (< 60s)
        assert result.duration_seconds <= 60
