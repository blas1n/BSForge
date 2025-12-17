"""Unit tests for Scene and SceneScript Pydantic models.

Tests cover:
- SceneType, VisualStyle, TransitionType, VisualHintType enums
- Scene model creation and validation
- Scene properties (inferred_visual_style, is_persona_scene, etc.)
- Scene duration estimation
- SceneScript model creation and validation
- SceneScript properties (full_text, has_commentary, etc.)
- SceneScript validation and transition recommendations
- SCENE_TYPE_STYLE_MAP and RECOMMENDED_TRANSITIONS mappings
"""

import pytest
from pydantic import ValidationError

from app.models.scene import (
    RECOMMENDED_TRANSITIONS,
    SCENE_TYPE_DURATION_ESTIMATES,
    SCENE_TYPE_STYLE_MAP,
    Scene,
    SceneScript,
    SceneType,
    TransitionType,
    VisualHintType,
    VisualStyle,
)


class TestSceneTypeEnum:
    """Test SceneType enum."""

    def test_scene_type_values(self) -> None:
        """Test SceneType enum values."""
        assert SceneType.HOOK == "hook"
        assert SceneType.INTRO == "intro"
        assert SceneType.CONTENT == "content"
        assert SceneType.EXAMPLE == "example"
        assert SceneType.COMMENTARY == "commentary"
        assert SceneType.REACTION == "reaction"
        assert SceneType.CONCLUSION == "conclusion"
        assert SceneType.CTA == "cta"

    def test_scene_type_count(self) -> None:
        """Test all scene types exist."""
        scene_types = [s.value for s in SceneType]
        assert len(scene_types) == 8

    def test_factual_scene_types(self) -> None:
        """Test factual scene types are correctly categorized."""
        factual_types = {SceneType.HOOK, SceneType.INTRO, SceneType.CONTENT, SceneType.EXAMPLE}
        for scene_type in factual_types:
            assert SCENE_TYPE_STYLE_MAP[scene_type] == VisualStyle.NEUTRAL

    def test_persona_scene_types(self) -> None:
        """Test persona scene types are correctly categorized."""
        persona_types = {SceneType.COMMENTARY, SceneType.REACTION}
        for scene_type in persona_types:
            assert SCENE_TYPE_STYLE_MAP[scene_type] == VisualStyle.PERSONA


class TestVisualStyleEnum:
    """Test VisualStyle enum."""

    def test_visual_style_values(self) -> None:
        """Test VisualStyle enum values."""
        assert VisualStyle.NEUTRAL == "neutral"
        assert VisualStyle.PERSONA == "persona"
        assert VisualStyle.EMPHASIS == "emphasis"

    def test_visual_style_count(self) -> None:
        """Test all visual styles exist."""
        styles = [s.value for s in VisualStyle]
        assert len(styles) == 3


class TestTransitionTypeEnum:
    """Test TransitionType enum."""

    def test_transition_type_values(self) -> None:
        """Test TransitionType enum values."""
        assert TransitionType.NONE == "none"
        assert TransitionType.FADE == "fade"
        assert TransitionType.CROSSFADE == "crossfade"
        assert TransitionType.ZOOM == "zoom"
        assert TransitionType.FLASH == "flash"
        assert TransitionType.SLIDE == "slide"

    def test_transition_type_count(self) -> None:
        """Test all transition types exist."""
        transitions = [t.value for t in TransitionType]
        assert len(transitions) == 6


class TestVisualHintTypeEnum:
    """Test VisualHintType enum."""

    def test_visual_hint_type_values(self) -> None:
        """Test VisualHintType enum values."""
        assert VisualHintType.STOCK_VIDEO == "stock_video"
        assert VisualHintType.STOCK_IMAGE == "stock_image"
        assert VisualHintType.AI_GENERATED == "ai_generated"
        assert VisualHintType.TEXT_OVERLAY == "text_overlay"
        assert VisualHintType.SOLID_COLOR == "solid_color"


class TestScene:
    """Test Scene Pydantic model."""

    def test_create_minimal_scene(self) -> None:
        """Test creating a scene with minimal required fields."""
        scene = Scene(
            scene_type=SceneType.CONTENT,
            text="이것은 테스트 장면입니다.",
        )

        assert scene.scene_type == SceneType.CONTENT
        assert scene.text == "이것은 테스트 장면입니다."
        assert scene.keyword is None
        assert scene.visual_hint == VisualHintType.STOCK_IMAGE
        assert scene.visual_style is None
        assert scene.transition_in == TransitionType.FADE
        assert scene.transition_out == TransitionType.FADE
        assert scene.emphasis_words == []
        assert scene.subtitle_segments is None

    def test_create_full_scene(self) -> None:
        """Test creating a scene with all fields."""
        scene = Scene(
            scene_type=SceneType.COMMENTARY,
            text="이건 진짜 대박이에요! AI가 이렇게 빠르게 발전할 줄 몰랐어요.",
            keyword="AI 발전",
            visual_hint=VisualHintType.AI_GENERATED,
            visual_style=VisualStyle.PERSONA,
            transition_in=TransitionType.FLASH,
            transition_out=TransitionType.FADE,
            emphasis_words=["대박", "AI"],
            subtitle_segments=[
                "이건 진짜 대박이에요!",
                "AI가 이렇게 빠르게",
                "발전할 줄 몰랐어요.",
            ],
        )

        assert scene.scene_type == SceneType.COMMENTARY
        assert scene.keyword == "AI 발전"
        assert scene.visual_hint == VisualHintType.AI_GENERATED
        assert scene.visual_style == VisualStyle.PERSONA
        assert scene.transition_in == TransitionType.FLASH
        assert "대박" in scene.emphasis_words
        assert len(scene.subtitle_segments) == 3

    def test_scene_empty_text_fails(self) -> None:
        """Test that empty text fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            Scene(scene_type=SceneType.CONTENT, text="")

        # Should have min_length validation error
        errors = exc_info.value.errors()
        assert any(
            "min_length" in str(e).lower() or "too_short" in str(e).get("type", "") for e in errors
        )

    def test_inferred_visual_style_from_scene_type(self) -> None:
        """Test visual style is correctly inferred from scene type."""
        # Factual scene -> NEUTRAL
        content_scene = Scene(scene_type=SceneType.CONTENT, text="정보 전달")
        assert content_scene.inferred_visual_style == VisualStyle.NEUTRAL

        # Persona scene -> PERSONA
        commentary_scene = Scene(scene_type=SceneType.COMMENTARY, text="내 생각은")
        assert commentary_scene.inferred_visual_style == VisualStyle.PERSONA

        # Emphasis scene -> EMPHASIS
        conclusion_scene = Scene(scene_type=SceneType.CONCLUSION, text="결론")
        assert conclusion_scene.inferred_visual_style == VisualStyle.EMPHASIS

    def test_explicit_visual_style_overrides_inferred(self) -> None:
        """Test explicit visual_style overrides inferred style."""
        scene = Scene(
            scene_type=SceneType.CONTENT,
            text="정보지만 강조 스타일",
            visual_style=VisualStyle.EMPHASIS,
        )

        # Explicit style should override
        assert scene.visual_style == VisualStyle.EMPHASIS
        assert scene.inferred_visual_style == VisualStyle.EMPHASIS

    def test_is_persona_scene(self) -> None:
        """Test is_persona_scene property."""
        # Persona scenes
        assert Scene(scene_type=SceneType.COMMENTARY, text="의견").is_persona_scene is True
        assert Scene(scene_type=SceneType.REACTION, text="리액션").is_persona_scene is True

        # Non-persona scenes
        assert Scene(scene_type=SceneType.CONTENT, text="정보").is_persona_scene is False
        assert Scene(scene_type=SceneType.HOOK, text="훅").is_persona_scene is False
        assert Scene(scene_type=SceneType.CONCLUSION, text="결론").is_persona_scene is False

    def test_is_factual_scene(self) -> None:
        """Test is_factual_scene property."""
        # Factual scenes
        assert Scene(scene_type=SceneType.HOOK, text="훅").is_factual_scene is True
        assert Scene(scene_type=SceneType.INTRO, text="인트로").is_factual_scene is True
        assert Scene(scene_type=SceneType.CONTENT, text="정보").is_factual_scene is True
        assert Scene(scene_type=SceneType.EXAMPLE, text="예시").is_factual_scene is True

        # Non-factual scenes
        assert Scene(scene_type=SceneType.COMMENTARY, text="의견").is_factual_scene is False
        assert Scene(scene_type=SceneType.CONCLUSION, text="결론").is_factual_scene is False

    def test_estimate_duration(self) -> None:
        """Test scene duration estimation."""
        # Short text
        short_scene = Scene(scene_type=SceneType.HOOK, text="짧은 훅 문장")
        duration = short_scene.estimate_duration()
        min_dur, max_dur = SCENE_TYPE_DURATION_ESTIMATES[SceneType.HOOK]
        assert min_dur <= duration <= max_dur

        # Long text - should be clamped to max
        long_text = " ".join(["단어"] * 100)  # 100 words
        long_scene = Scene(scene_type=SceneType.CONTENT, text=long_text)
        duration = long_scene.estimate_duration()
        _, max_dur = SCENE_TYPE_DURATION_ESTIMATES[SceneType.CONTENT]
        assert duration <= max_dur

    def test_estimate_duration_with_custom_wpm(self) -> None:
        """Test duration estimation with custom words per minute."""
        scene = Scene(scene_type=SceneType.CONTENT, text="This is a test sentence with eight words")

        # Slower speaking rate should give longer duration
        slow_duration = scene.estimate_duration(words_per_minute=100)
        fast_duration = scene.estimate_duration(words_per_minute=200)

        # Clamping may affect this, but the trend should hold
        assert slow_duration >= fast_duration


class TestSceneScript:
    """Test SceneScript Pydantic model."""

    def test_create_minimal_script(self) -> None:
        """Test creating a script with minimal fields."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="충격적인 사실!"),
            ]
        )

        assert len(script.scenes) == 1
        assert script.title_text is None

    def test_create_full_script(self) -> None:
        """Test creating a complete script."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="AI가 세상을 바꾸고 있습니다"),
                Scene(scene_type=SceneType.INTRO, text="오늘은 AI 발전에 대해 알아보겠습니다"),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="2024년 기준 전 세계 기업의 70%가 AI를 도입했습니다",
                ),
                Scene(scene_type=SceneType.COMMENTARY, text="이건 정말 놀라운 속도예요"),
                Scene(scene_type=SceneType.CONCLUSION, text="AI 시대가 본격적으로 시작됐습니다"),
            ],
            title_text="AI 혁명의 시작",
        )

        assert len(script.scenes) == 5
        assert script.title_text == "AI 혁명의 시작"

    def test_empty_scenes_fails(self) -> None:
        """Test that empty scenes list fails validation."""
        with pytest.raises(ValidationError):
            SceneScript(scenes=[])

    def test_total_estimated_duration(self) -> None:
        """Test total duration estimation."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용"),
                Scene(scene_type=SceneType.CONCLUSION, text="결론"),
            ]
        )

        duration = script.total_estimated_duration
        assert duration > 0
        # Should be sum of individual scene durations
        expected = sum(scene.estimate_duration() for scene in script.scenes)
        assert duration == expected

    def test_full_text(self) -> None:
        """Test full text concatenation."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="첫 번째"),
                Scene(scene_type=SceneType.CONTENT, text="두 번째"),
                Scene(scene_type=SceneType.CONCLUSION, text="세 번째"),
            ]
        )

        assert script.full_text == "첫 번째 두 번째 세 번째"

    def test_scene_types(self) -> None:
        """Test scene_types property."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용"),
                Scene(scene_type=SceneType.COMMENTARY, text="의견"),
            ]
        )

        assert script.scene_types == [SceneType.HOOK, SceneType.CONTENT, SceneType.COMMENTARY]

    def test_has_commentary(self) -> None:
        """Test has_commentary property."""
        # With commentary
        with_commentary = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.COMMENTARY, text="의견"),
            ]
        )
        assert with_commentary.has_commentary is True

        # With reaction
        with_reaction = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.REACTION, text="리액션"),
            ]
        )
        assert with_reaction.has_commentary is True

        # Without persona scenes
        without_commentary = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용"),
            ]
        )
        assert without_commentary.has_commentary is False

    def test_validate_structure_valid(self) -> None:
        """Test validation for valid script structure."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="충격적인 AI 뉴스가 있습니다"),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="오늘 발표된 내용에 따르면 AI가 크게 발전했습니다",
                ),
                Scene(
                    scene_type=SceneType.COMMENTARY,
                    text=(
                        "제 생각에는 이게 정말 큰 변화의 시작이에요 "
                        "앞으로 더 많은 발전이 있을 것 같습니다"
                    ),
                ),
                Scene(scene_type=SceneType.CONCLUSION, text="이상 AI 뉴스였습니다 감사합니다"),
            ]
        )

        errors = script.validate_structure()
        # Should have no major errors (might have duration warning)
        structural_errors = [
            e for e in errors if "HOOK" in e or "CONTENT" in e or "COMMENTARY" in e
        ]
        assert len(structural_errors) == 0

    def test_validate_structure_no_hook_first(self) -> None:
        """Test validation error when first scene is not HOOK."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.CONTENT, text="내용부터 시작"),
                Scene(scene_type=SceneType.CONCLUSION, text="결론"),
            ]
        )

        errors = script.validate_structure()
        assert any("HOOK" in e for e in errors)

    def test_validate_structure_no_content(self) -> None:
        """Test validation error when no content/commentary."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅만 있는 영상"),
            ]
        )

        errors = script.validate_structure()
        assert any("CONTENT" in e or "COMMENTARY" in e for e in errors)

    def test_validate_structure_no_commentary_warning(self) -> None:
        """Test validation warning when no commentary (BSForge differentiator)."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용만 있는 영상 페르소나 의견 없음"),
                Scene(scene_type=SceneType.CONCLUSION, text="결론"),
            ]
        )

        errors = script.validate_structure()
        assert any("COMMENTARY" in e or "REACTION" in e for e in errors)
        assert any("BSForge" in e for e in errors)

    def test_validate_structure_too_short(self) -> None:
        """Test validation error for too short script."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="짧음"),
            ]
        )

        errors = script.validate_structure()
        assert any("short" in e.lower() for e in errors)

    def test_get_recommended_transitions(self) -> None:
        """Test recommended transitions between scenes."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용"),
                Scene(scene_type=SceneType.COMMENTARY, text="의견"),
                Scene(scene_type=SceneType.CONCLUSION, text="결론"),
            ]
        )

        transitions = script.get_recommended_transitions()
        assert len(transitions) == 3  # n-1 transitions for n scenes

        # HOOK -> CONTENT: FADE
        assert transitions[0] == TransitionType.FADE
        # CONTENT -> COMMENTARY: FLASH (key differentiator!)
        assert transitions[1] == TransitionType.FLASH
        # COMMENTARY -> CONCLUSION: FADE
        assert transitions[2] == TransitionType.FADE

    def test_get_recommended_transitions_single_scene(self) -> None:
        """Test recommended transitions for single scene (empty)."""
        script = SceneScript(scenes=[Scene(scene_type=SceneType.HOOK, text="훅만")])

        transitions = script.get_recommended_transitions()
        assert transitions == []

    def test_apply_recommended_transitions(self) -> None:
        """Test applying recommended transitions to scenes."""
        script = SceneScript(
            scenes=[
                Scene(scene_type=SceneType.HOOK, text="훅"),
                Scene(scene_type=SceneType.CONTENT, text="내용"),
                Scene(scene_type=SceneType.COMMENTARY, text="의견"),
            ]
        )

        # Before applying
        assert script.scenes[0].transition_out == TransitionType.FADE
        assert script.scenes[1].transition_in == TransitionType.FADE

        # Apply recommended
        script.apply_recommended_transitions()

        # After applying - HOOK -> CONTENT: FADE
        assert script.scenes[0].transition_out == TransitionType.FADE
        assert script.scenes[1].transition_in == TransitionType.FADE

        # CONTENT -> COMMENTARY: FLASH
        assert script.scenes[1].transition_out == TransitionType.FLASH
        assert script.scenes[2].transition_in == TransitionType.FLASH


class TestSceneTypeMappings:
    """Test SCENE_TYPE_STYLE_MAP and RECOMMENDED_TRANSITIONS."""

    def test_all_scene_types_have_style_mapping(self) -> None:
        """Test all scene types are in SCENE_TYPE_STYLE_MAP."""
        for scene_type in SceneType:
            assert scene_type in SCENE_TYPE_STYLE_MAP

    def test_all_scene_types_have_duration_estimates(self) -> None:
        """Test all scene types are in SCENE_TYPE_DURATION_ESTIMATES."""
        for scene_type in SceneType:
            assert scene_type in SCENE_TYPE_DURATION_ESTIMATES
            min_dur, max_dur = SCENE_TYPE_DURATION_ESTIMATES[scene_type]
            assert min_dur > 0
            assert max_dur >= min_dur

    def test_fact_to_opinion_uses_flash_transition(self) -> None:
        """Test Fact->Opinion transition uses FLASH (key differentiator)."""
        key_transitions = [
            (SceneType.CONTENT, SceneType.COMMENTARY),
            (SceneType.EXAMPLE, SceneType.COMMENTARY),
            (SceneType.HOOK, SceneType.COMMENTARY),
        ]

        for from_type, to_type in key_transitions:
            key = (from_type, to_type)
            assert key in RECOMMENDED_TRANSITIONS
            assert RECOMMENDED_TRANSITIONS[key] == TransitionType.FLASH

    def test_conclusion_to_cta_uses_none_transition(self) -> None:
        """Test CONCLUSION->CTA has no transition."""
        key = (SceneType.CONCLUSION, SceneType.CTA)
        assert key in RECOMMENDED_TRANSITIONS
        assert RECOMMENDED_TRANSITIONS[key] == TransitionType.NONE
