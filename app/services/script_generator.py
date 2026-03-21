"""Prompt-based script generation service.

Generates scene-structured YouTube Shorts scripts using LLM prompts.
Replaces the RAG-based generator with a simpler, direct approach.
"""

import json
import re
from dataclasses import dataclass

from app.config.persona import PersonaConfig
from app.core.logging import get_logger
from app.infrastructure.llm import LLMClient, LLMConfig
from app.models.scene import Scene, SceneScript
from app.prompts.manager import PromptManager, PromptType

logger = get_logger(__name__)


@dataclass
class ScriptGenerationResult:
    """Result of script generation.

    Attributes:
        scene_script: Parsed SceneScript with scenes and headline
        raw_response: Raw LLM response text
        model: LLM model used
    """

    scene_script: SceneScript
    raw_response: str
    model: str


class ScriptGenerator:
    """Generate scripts from topics using LLM prompts.

    Uses the scene_script_generation.yaml prompt template to generate
    scene-structured scripts with persona-driven commentary.

    Example:
        >>> generator = ScriptGenerator(llm_client=client, prompt_manager=pm)
        >>> result = await generator.generate(
        ...     topic_title="AI 뉴스",
        ...     topic_summary="요약",
        ...     topic_terms=["AI"],
        ...     persona=persona_config,
        ... )
    """

    # Default LLM timeout for script generation (seconds)
    DEFAULT_TIMEOUT: int = 90

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        timeout: int | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self._timeout = timeout or self.DEFAULT_TIMEOUT

    async def generate(
        self,
        topic_title: str,
        topic_summary: str,
        topic_terms: list[str],
        persona: PersonaConfig | None = None,
        target_duration: int = 25,
        video_format: str = "YouTube Shorts",
    ) -> ScriptGenerationResult:
        """Generate a scene-based script from topic info.

        Args:
            topic_title: Topic title
            topic_summary: Topic summary
            topic_terms: Topic keywords
            persona: Optional persona configuration
            target_duration: Target video duration in seconds
            video_format: Video format type

        Returns:
            ScriptGenerationResult with parsed SceneScript

        Raises:
            ValueError: If topic_title or topic_summary is empty
        """
        if not topic_title.strip():
            raise ValueError("topic_title cannot be empty")
        if not topic_summary.strip():
            raise ValueError("topic_summary cannot be empty")

        # Build template variables
        variables = self._build_variables(
            topic_title=topic_title,
            topic_summary=topic_summary,
            topic_terms=topic_terms,
            persona=persona,
            target_duration=target_duration,
            video_format=video_format,
        )

        # Render prompt
        prompt = self.prompt_manager.render(PromptType.SCRIPT_GENERATION, **variables)

        # Get LLM settings from template
        llm_settings = self.prompt_manager.get_llm_settings(PromptType.SCRIPT_GENERATION)
        llm_config = LLMConfig.from_prompt_settings(llm_settings, timeout=self._timeout)

        # Call LLM
        logger.info("generating_script", topic=topic_title, model=llm_config.model)

        try:
            response = await self.llm_client.complete(
                config=llm_config,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            logger.exception("script_llm_call_failed", topic=topic_title, model=llm_config.model)
            raise

        # Parse response into SceneScript
        try:
            scene_script = self._parse_response(response.content)
        except ValueError:
            logger.error("script_parse_failed", topic=topic_title, model=llm_config.model)
            raise

        logger.info(
            "script_generated",
            topic=topic_title,
            scenes=len(scene_script.scenes),
            headline=scene_script.headline,
        )

        return ScriptGenerationResult(
            scene_script=scene_script,
            raw_response=response.content,
            model=response.model,
        )

    def _build_variables(
        self,
        topic_title: str,
        topic_summary: str,
        topic_terms: list[str],
        persona: PersonaConfig | None,
        target_duration: int,
        video_format: str,
    ) -> dict[str, object]:
        """Build template variables from inputs."""
        from datetime import datetime, timezone

        variables: dict[str, object] = {
            "topic_title": topic_title,
            "topic_summary": topic_summary,
            "topic_terms": topic_terms,
            "target_duration": target_duration,
            "video_format": video_format,
            "current_date": datetime.now(tz=timezone.utc).date().isoformat(),  # noqa: UP017
            # Defaults for optional template variables (use empty values, not None,
            # to avoid "None" string rendering in Mako templates)
            "persona_name": "",
            "persona_tagline": "",
            "persona_description": "",
            "persona_expertise": "",
            "communication_tone": "",
            "sentence_endings": [],
            "connectors": [],
            "perspective_values": [],
            "perspective_biases": [],
            "perspective_contrarian": False,
            "avoid_words": [],
            "similar_content": "",
            "opinions": "",
            "examples": "",
            "hooks": "",
            "enriched_cluster_summary": "",
            "enriched_cluster_sources": "",
            "enriched_research_results": "",
        }

        if persona:
            variables["persona_name"] = persona.name
            variables["persona_tagline"] = persona.tagline

            if persona.communication:
                variables["communication_tone"] = persona.communication.tone
                if persona.communication.speech_patterns:
                    variables["sentence_endings"] = (
                        persona.communication.speech_patterns.sentence_endings
                    )
                    variables["connectors"] = persona.communication.speech_patterns.connectors
                if persona.communication.avoid_patterns:
                    variables["avoid_words"] = persona.communication.avoid_patterns.words

            if persona.perspective:
                variables["perspective_values"] = persona.perspective.core_values
                variables["perspective_contrarian"] = bool(persona.perspective.contrarian_views)

        return variables

    def _parse_response(self, content: str) -> SceneScript:
        """Parse LLM response JSON into SceneScript.

        Args:
            content: Raw LLM response text (should be JSON)

        Returns:
            Parsed SceneScript

        Raises:
            ValueError: If response cannot be parsed
        """
        # Strip markdown code blocks if present
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: extract the outermost JSON object from the response
            try:
                start = cleaned.index("{")
                end = cleaned.rindex("}") + 1
                data = json.loads(cleaned[start:end])
            except (ValueError, json.JSONDecodeError) as e:
                raise ValueError(f"Failed to parse LLM response as JSON: {e}") from e

        headline = data.get("headline", "")
        scenes_data = data.get("scenes", [])

        if not scenes_data:
            raise ValueError("LLM response contains no scenes")

        try:
            scenes = [Scene(**scene_data) for scene_data in scenes_data]
            return SceneScript(scenes=scenes, headline=headline)
        except Exception as e:
            raise ValueError(f"Invalid scene data in LLM response: {e}") from e


__all__ = [
    "ScriptGenerator",
    "ScriptGenerationResult",
]
