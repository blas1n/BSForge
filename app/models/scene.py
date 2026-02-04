"""Scene data models for scene-based video generation.

This module defines the core data structures for BSForge's scene-based
video generation system. Key features:
- SceneType enum with COMMENTARY/REACTION for persona opinions (BSForge differentiator)
- VisualStyle enum for fact vs opinion visual differentiation
- TransitionType enum for scene transitions
- Scene and SceneScript Pydantic models
"""

from enum import Enum

from pydantic import BaseModel, Field


class SceneType(str, Enum):
    """Scene type classification.

    BSForge differentiator: COMMENTARY and REACTION types allow
    AI persona to express opinions/interpretations, not just facts.
    """

    # 정보 전달 (Factual)
    HOOK = "hook"  # 0-3초, 주의 끌기
    INTRO = "intro"  # 3-5초, 맥락 설정
    CONTENT = "content"  # 5-10초, 핵심 정보 (여러 개 가능)
    EXAMPLE = "example"  # 3-5초, 구체적 예시

    # 페르소나 의견 (Commentary) ← BSForge 핵심 차별점
    COMMENTARY = "commentary"  # 3-8초, 페르소나 생각/해석/의견
    REACTION = "reaction"  # 2-4초, 짧은 리액션 ("이건 진짜 대박이에요")

    # 마무리
    CONCLUSION = "conclusion"  # 2-4초, 요약/마무리
    CTA = "cta"  # 2-3초, 행동 유도 (선택적)


class VisualStyle(str, Enum):
    """Visual style for scene rendering.

    Each style has different visual treatment:
    - NEUTRAL: Standard info delivery (white text, 30% overlay)
    - PERSONA: Opinion scenes (accent color, left border, larger text)
    - EMPHASIS: Conclusion/CTA (background box, extra bold)
    """

    NEUTRAL = "neutral"  # 정보 전달용 (HOOK, INTRO, CONTENT, EXAMPLE)
    PERSONA = "persona"  # 페르소나 의견용 (COMMENTARY, REACTION)
    EMPHASIS = "emphasis"  # 강조용 (CONCLUSION, CTA)


class TransitionType(str, Enum):
    """Transition effect between scenes."""

    NONE = "none"  # No transition
    FADE = "fade"  # 0.3-0.5초, standard fade
    CROSSFADE = "crossfade"  # 0.4-0.6초, overlap fade
    ZOOM = "zoom"  # 0.3초, zoom in/out effect
    FLASH = "flash"  # 0.033초 (1 frame), color flash for Fact→Opinion
    SLIDE = "slide"  # 0.4-0.6초, slide in from edge


# Scene type to visual style mapping
SCENE_TYPE_STYLE_MAP: dict[SceneType, VisualStyle] = {
    SceneType.HOOK: VisualStyle.NEUTRAL,
    SceneType.INTRO: VisualStyle.NEUTRAL,
    SceneType.CONTENT: VisualStyle.NEUTRAL,
    SceneType.EXAMPLE: VisualStyle.NEUTRAL,
    SceneType.COMMENTARY: VisualStyle.PERSONA,
    SceneType.REACTION: VisualStyle.PERSONA,
    SceneType.CONCLUSION: VisualStyle.EMPHASIS,
    SceneType.CTA: VisualStyle.EMPHASIS,
}

# Recommended transitions between scene types
RECOMMENDED_TRANSITIONS: dict[tuple[SceneType, SceneType], TransitionType] = {
    # Fact → Fact: 부드러운 전환
    (SceneType.HOOK, SceneType.INTRO): TransitionType.FADE,
    (SceneType.HOOK, SceneType.CONTENT): TransitionType.FADE,
    (SceneType.INTRO, SceneType.CONTENT): TransitionType.FADE,
    (SceneType.CONTENT, SceneType.CONTENT): TransitionType.CROSSFADE,
    (SceneType.CONTENT, SceneType.EXAMPLE): TransitionType.SLIDE,
    (SceneType.EXAMPLE, SceneType.CONTENT): TransitionType.SLIDE,
    # Fact → Opinion: 강조 전환 (핵심!)
    (SceneType.CONTENT, SceneType.COMMENTARY): TransitionType.FLASH,
    (SceneType.EXAMPLE, SceneType.COMMENTARY): TransitionType.FLASH,
    (SceneType.HOOK, SceneType.COMMENTARY): TransitionType.FLASH,
    (SceneType.HOOK, SceneType.REACTION): TransitionType.ZOOM,
    (SceneType.CONTENT, SceneType.REACTION): TransitionType.ZOOM,
    # Opinion → Fact: 부드러운 복귀
    (SceneType.COMMENTARY, SceneType.CONTENT): TransitionType.FADE,
    (SceneType.COMMENTARY, SceneType.EXAMPLE): TransitionType.FADE,
    (SceneType.REACTION, SceneType.CONTENT): TransitionType.FADE,
    # Opinion → Opinion
    (SceneType.COMMENTARY, SceneType.REACTION): TransitionType.FADE,
    (SceneType.REACTION, SceneType.COMMENTARY): TransitionType.FADE,
    # 마무리
    (SceneType.CONTENT, SceneType.CONCLUSION): TransitionType.FADE,
    (SceneType.COMMENTARY, SceneType.CONCLUSION): TransitionType.FADE,
    (SceneType.REACTION, SceneType.CONCLUSION): TransitionType.FADE,
    (SceneType.CONCLUSION, SceneType.CTA): TransitionType.NONE,
}

# Default duration estimates per scene type (seconds)
SCENE_TYPE_DURATION_ESTIMATES: dict[SceneType, tuple[float, float]] = {
    SceneType.HOOK: (2.0, 3.0),
    SceneType.INTRO: (3.0, 5.0),
    SceneType.CONTENT: (5.0, 10.0),
    SceneType.EXAMPLE: (3.0, 5.0),
    SceneType.COMMENTARY: (3.0, 8.0),
    SceneType.REACTION: (2.0, 4.0),
    SceneType.CONCLUSION: (2.0, 4.0),
    SceneType.CTA: (2.0, 3.0),
}


class Scene(BaseModel):
    """Individual scene in a script.

    Attributes:
        scene_type: Classification of the scene (hook, content, commentary, etc.)
        text: Display text for subtitles (original notation: GPT-4, Claude 3.5)
        tts_text: TTS pronunciation text (optional, only when differs from text)
        visual_keyword: English keyword for visual search
        visual_style: Override visual style (auto-inferred from scene_type if None)
        transition_in: Transition effect entering this scene
        transition_out: Transition effect leaving this scene
        emphasis_words: Words to highlight in subtitles
        subtitle_segments: Manual subtitle segment breaks (overrides TTS-based segmentation)

    Example:
        Scene(
            scene_type=SceneType.CONTENT,
            text="GPT-4 대비 5분의 1 가격이거든요.",
            tts_text="GPT 사 대비 5분의 1 가격이거든요.",
            emphasis_words=["5분의 1"],
        )
    """

    scene_type: SceneType
    text: str = Field(..., min_length=1, description="Display text for subtitles")
    tts_text: str | None = Field(
        default=None,
        description="TTS pronunciation text (only when different from text). "
        "E.g., 'GPT 사' for 'GPT-4', '클로드 삼점오' for 'Claude 3.5'",
    )

    # Visual
    visual_keyword: str | None = Field(
        default=None,
        description="English keyword for visual search (Pexels/Pixabay/Stable Diffusion). "
        "Should be 3-5 descriptive English words. Example: 'excited fans cheering concert'",
    )
    requires_web_search: bool = Field(
        default=False,
        description="True if visual_keyword refers to a specific real person, celebrity, "
        "brand, or entity that requires web image search (not stock images). "
        "Examples: 'Taylor Swift', 'BTS Jungkook', 'Apple logo', 'Tesla Cybertruck'",
    )
    visual_style: VisualStyle | None = Field(
        default=None,
        description="Override visual style (auto-inferred if None)",
    )

    # Transition
    transition_in: TransitionType = Field(
        default=TransitionType.FADE,
        description="Transition effect entering this scene",
    )
    transition_out: TransitionType = Field(
        default=TransitionType.FADE,
        description="Transition effect leaving this scene",
    )

    # Subtitle
    emphasis_words: list[str] = Field(
        default_factory=list,
        description="Words to highlight in subtitles",
    )
    subtitle_segments: list[str] | None = Field(
        default=None,
        description="Manual subtitle segment breaks (문맥에 맞게 끊기). "
        "If None, auto-split based on TTS word boundaries or character count.",
    )

    @property
    def tts_content(self) -> str:
        """Get text for TTS synthesis (tts_text if set, else text)."""
        return self.tts_text if self.tts_text else self.text

    @property
    def inferred_visual_style(self) -> VisualStyle:
        """Get visual style (explicit or inferred from scene_type)."""
        if self.visual_style is not None:
            return self.visual_style
        return SCENE_TYPE_STYLE_MAP.get(self.scene_type, VisualStyle.NEUTRAL)

    @property
    def is_persona_scene(self) -> bool:
        """Check if this is a persona opinion scene."""
        return self.scene_type in (SceneType.COMMENTARY, SceneType.REACTION)

    @property
    def is_factual_scene(self) -> bool:
        """Check if this is a factual information scene."""
        return self.scene_type in (
            SceneType.HOOK,
            SceneType.INTRO,
            SceneType.CONTENT,
            SceneType.EXAMPLE,
        )

    def estimate_duration(self, words_per_minute: int = 150) -> float:
        """Estimate duration based on text length.

        Args:
            words_per_minute: Speaking rate for estimation

        Returns:
            Estimated duration in seconds
        """
        word_count = len(self.text.split())
        estimated = (word_count / words_per_minute) * 60

        # Clamp to scene type's expected range
        min_dur, max_dur = SCENE_TYPE_DURATION_ESTIMATES.get(self.scene_type, (2.0, 10.0))
        return max(min_dur, min(estimated, max_dur))


class SceneScript(BaseModel):
    """Complete scene-based script.

    Attributes:
        scenes: List of scenes in order
        headline: Video headline
    """

    scenes: list[Scene] = Field(..., min_length=1, description="List of scenes")
    headline: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Video headline (max 20 chars, e.g., '테슬라, 완전 망했다')",
    )

    @property
    def total_estimated_duration(self) -> float:
        """Get total estimated duration in seconds."""
        return sum(scene.estimate_duration() for scene in self.scenes)

    @property
    def full_text(self) -> str:
        """Get combined text of all scenes."""
        return " ".join(scene.text for scene in self.scenes)

    @property
    def scene_types(self) -> list[SceneType]:
        """Get list of scene types in order."""
        return [scene.scene_type for scene in self.scenes]

    @property
    def has_commentary(self) -> bool:
        """Check if script has at least one commentary/reaction scene."""
        return any(
            scene.scene_type in (SceneType.COMMENTARY, SceneType.REACTION) for scene in self.scenes
        )

    def validate_structure(self) -> list[str]:
        """Validate script structure.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []
        types = self.scene_types

        # Hook should be first
        if types and types[0] != SceneType.HOOK:
            errors.append("First scene should be HOOK")

        # Must have at least one content or commentary scene
        has_substance = any(t in (SceneType.CONTENT, SceneType.COMMENTARY) for t in types)
        if not has_substance:
            errors.append("Must have at least one CONTENT or COMMENTARY scene")

        # BSForge differentiator: recommend commentary
        if not self.has_commentary:
            errors.append(
                "Recommend at least one COMMENTARY or REACTION scene "
                "for persona voice (BSForge differentiator)"
            )

        # Duration check
        duration = self.total_estimated_duration
        if duration < 15:
            errors.append(f"Script too short: {duration:.1f}s (min 15s recommended)")
        if duration > 60:
            errors.append(f"Script too long: {duration:.1f}s (max 60s for Shorts)")

        return errors

    def get_recommended_transitions(self) -> list[TransitionType]:
        """Get recommended transitions between scenes.

        Returns:
            List of transition types (length = len(scenes) - 1)
        """
        if len(self.scenes) < 2:
            return []

        transitions: list[TransitionType] = []
        for i in range(len(self.scenes) - 1):
            current_type = self.scenes[i].scene_type
            next_type = self.scenes[i + 1].scene_type
            key = (current_type, next_type)

            # Use recommended transition or default to FADE
            transition = RECOMMENDED_TRANSITIONS.get(key, TransitionType.FADE)
            transitions.append(transition)

        return transitions

    def apply_recommended_transitions(self) -> None:
        """Apply recommended transitions to all scenes in place."""
        transitions = self.get_recommended_transitions()

        for i, transition in enumerate(transitions):
            self.scenes[i].transition_out = transition
            self.scenes[i + 1].transition_in = transition
