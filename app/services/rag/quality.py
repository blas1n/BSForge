"""Script quality checking services.

This module provides quality scoring and validation for generated scripts.
Extracted from generator.py for better separation of concerns.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config.rag import QualityCheckConfig
from app.core.config_loader import load_quality_config
from app.core.logging import get_logger
from app.models.channel import Persona
from app.models.scene import SceneScript, SceneType

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_quality_defaults() -> dict[str, Any]:
    """Get quality defaults from config/quality.yaml."""
    return load_quality_config()


@dataclass
class QualityResult:
    """Result of quality check.

    Attributes:
        passed: Whether quality check passed
        style_score: Style consistency score (0-1)
        hook_score: Hook quality score (0-1)
        forbidden_words: List of forbidden words found
        word_count: Total word count
        estimated_duration: Estimated duration in seconds
    """

    passed: bool
    style_score: float
    hook_score: float
    forbidden_words: list[str]
    word_count: int
    estimated_duration: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "passed": self.passed,
            "style_score": self.style_score,
            "hook_score": self.hook_score,
            "forbidden_words": self.forbidden_words,
            "word_count": self.word_count,
            "estimated_duration": self.estimated_duration,
        }


class ScriptQualityChecker:
    """Check and score script quality.

    Provides quality metrics for generated scripts including:
    - Style consistency with persona
    - Hook effectiveness
    - Forbidden word detection
    - Duration estimation

    Attributes:
        config: Quality check configuration
    """

    def __init__(self, config: QualityCheckConfig | None = None) -> None:
        """Initialize quality checker.

        Args:
            config: Quality check configuration (uses defaults if None)
        """
        self.config = config or QualityCheckConfig()

    def check_script(
        self,
        script_text: str,
        persona: Persona,
        hook_text: str | None = None,
    ) -> QualityResult:
        """Check script quality.

        Args:
            script_text: Full script text
            persona: Persona DB model
            hook_text: Optional separate hook text (extracted from script if None)

        Returns:
            QualityResult with all metrics
        """
        word_count = len(script_text.split())
        estimated_duration = self.estimate_duration(script_text)
        style_score = self.calculate_style_score(script_text, persona)
        forbidden_words = self.find_forbidden_words(script_text, persona)

        # Extract hook from script if not provided
        if hook_text is None:
            hook_text = self._extract_hook(script_text)
        hook_score = self.evaluate_hook(hook_text)

        # Determine if passed
        passed = (
            style_score >= self.config.min_style_score
            and hook_score >= self.config.min_hook_score
            and len(forbidden_words) <= self.config.max_forbidden_words
        )

        return QualityResult(
            passed=passed,
            style_score=style_score,
            hook_score=hook_score,
            forbidden_words=forbidden_words,
            word_count=word_count,
            estimated_duration=estimated_duration,
        )

    def check_scene_script(
        self,
        scene_script: SceneScript,
        persona: Persona,
    ) -> QualityResult:
        """Check scene script quality.

        Args:
            scene_script: SceneScript object
            persona: Persona DB model

        Returns:
            QualityResult with all metrics
        """
        full_text = scene_script.full_text
        word_count = len(full_text.split())
        estimated_duration = self.estimate_duration(full_text)
        style_score = self.calculate_style_score(full_text, persona)
        forbidden_words = self.find_forbidden_words(full_text, persona)

        # Get hook from first scene (usually HOOK type)
        hook_text = ""
        for scene in scene_script.scenes:
            if scene.scene_type == SceneType.HOOK:
                hook_text = scene.text
                break
        if not hook_text and scene_script.scenes:
            hook_text = scene_script.scenes[0].text

        hook_score = self.evaluate_hook(hook_text)

        # Determine if passed
        passed = (
            style_score >= self.config.min_style_score
            and hook_score >= self.config.min_hook_score
            and len(forbidden_words) <= self.config.max_forbidden_words
        )

        return QualityResult(
            passed=passed,
            style_score=style_score,
            hook_score=hook_score,
            forbidden_words=forbidden_words,
            word_count=word_count,
            estimated_duration=estimated_duration,
        )

    def estimate_duration(self, script_text: str) -> int:
        """Estimate script duration in seconds.

        Uses words_per_minute from config/quality.yaml for natural speech rate.

        Args:
            script_text: Script text

        Returns:
            Estimated duration in seconds
        """
        defaults = _get_quality_defaults()
        script_config = defaults.get("script", {})
        words_per_minute = script_config.get("words_per_minute", 150)

        word_count = len(script_text.split())
        duration_seconds = int((word_count / words_per_minute) * 60)
        return duration_seconds

    def calculate_style_score(self, script_text: str, persona: Persona) -> float:
        """Calculate style consistency score.

        Simple heuristic: check for persona-specific patterns.
        For production, use LLM-based style classification.

        Args:
            script_text: Script text
            persona: Persona DB model

        Returns:
            Style score (0-1)
        """
        score = 0.7  # Base score

        if not persona.communication_style:
            return score

        text_lower = script_text.lower()

        # Check for preferred connectors
        if "connectors" in persona.communication_style:
            connectors = persona.communication_style["connectors"]
            found_connectors = sum(1 for c in connectors if c.lower() in text_lower)
            if connectors:
                score += 0.1 * (found_connectors / len(connectors))

        # Check for sentence endings
        if "sentence_endings" in persona.communication_style:
            endings = persona.communication_style["sentence_endings"]
            found_endings = sum(1 for e in endings if e.lower() in text_lower)
            if endings:
                score += 0.1 * (found_endings / len(endings))

        # Check for avoid words (penalize if found)
        if "avoid_words" in persona.communication_style:
            avoid_words = persona.communication_style["avoid_words"]
            found_avoid = sum(1 for w in avoid_words if w.lower() in text_lower)
            if found_avoid > 0:
                score -= 0.2 * (found_avoid / max(len(avoid_words), 1))

        return max(0.0, min(1.0, score))

    def evaluate_hook(self, hook: str) -> float:
        """Evaluate hook quality.

        Simple heuristic: check for attention-grabbing patterns.
        For production, use LLM-based hook classification.

        Args:
            hook: Hook text

        Returns:
            Hook score (0-1)
        """
        if not hook:
            return 0.0

        score = 0.5  # Base score

        hook_lower = hook.lower()

        # Question hooks
        if "?" in hook:
            score += 0.2

        # Surprising statements
        surprising_patterns = [
            "you won't believe",
            "surprising",
            "shocking",
            "what if",
            "imagine",
            "놀랍게도",
            "믿기 힘들지만",
            "만약",
        ]
        if any(pattern in hook_lower for pattern in surprising_patterns):
            score += 0.15

        # Numbers (concrete facts)
        if re.search(r"\d+", hook):
            score += 0.1

        # Short and punchy (3-15 words)
        word_count = len(hook.split())
        if 3 <= word_count <= 15:
            score += 0.15

        return min(1.0, score)

    def find_forbidden_words(self, script_text: str, persona: Persona) -> list[str]:
        """Find forbidden words in script.

        Args:
            script_text: Script text
            persona: Persona DB model

        Returns:
            List of forbidden words found
        """
        if not persona.communication_style or "avoid_words" not in persona.communication_style:
            return []

        forbidden = persona.communication_style["avoid_words"]
        text_lower = script_text.lower()

        found = [word for word in forbidden if word.lower() in text_lower]
        return found

    def _extract_hook(self, script_text: str) -> str:
        """Extract hook from script text.

        Takes the first sentence or paragraph as hook.

        Args:
            script_text: Full script text

        Returns:
            Hook text
        """
        # Try to find first paragraph
        paragraphs = script_text.strip().split("\n\n")
        if paragraphs:
            first_para = paragraphs[0].strip()
            # If very long, take first sentence
            if len(first_para) > 200:
                sentences = re.split(r"[.!?]", first_para)
                if sentences:
                    return sentences[0].strip()
            return first_para
        return script_text[:200] if len(script_text) > 200 else script_text


__all__ = [
    "QualityResult",
    "ScriptQualityChecker",
]
