"""RAG prompt building services.

This module provides persona-aware prompt construction for script generation using
centralized template management.
"""

from typing import Any

from app.core.logging import get_logger
from app.prompts.manager import PromptManager, PromptType
from app.services.rag.context import GenerationContext

logger = get_logger(__name__)


class PromptBuilder:
    """Build persona-aware prompts for Claude using centralized templates.

    Uses PromptManager to load and render templates from prompts/templates/.
    Templates are written in Mako format with variable substitution.
    """

    def __init__(self, prompt_manager: PromptManager) -> None:
        """Initialize PromptBuilder with PromptManager.

        Args:
            prompt_manager: PromptManager for loading templates
        """
        self.prompt_manager = prompt_manager

    async def build_prompt(self, context: GenerationContext) -> str:
        """Build scene-based generation prompt.

        Generates JSON array of scenes with explicit scene types including
        COMMENTARY/REACTION for persona opinions (BSForge differentiator).

        Args:
            context: Generation context with topic, persona, and retrieved content

        Returns:
            Formatted prompt string for scene-based script generation
        """
        logger.info("Building generation prompt")

        # Extract variables for template rendering
        variables = self._build_template_variables(context)

        # Render using PromptManager
        prompt = self.prompt_manager.render(PromptType.SCRIPT_GENERATION, **variables)

        logger.debug(f"Built prompt: {len(prompt)} characters")
        return prompt

    def _build_template_variables(
        self, context: GenerationContext
    ) -> dict[str, str | int | list[Any] | None | bool]:
        """Build template variables from context.

        Args:
            context: Generation context

        Returns:
            Dictionary of template variables for Mako template
        """
        persona = context.persona
        topic = context.topic
        retrieved = context.retrieved
        config = context.config

        variables: dict[str, str | int | list[Any] | None | bool] = {}

        # Persona variables
        variables["persona_name"] = persona.name if persona.name else None
        variables["persona_tagline"] = persona.tagline if persona.tagline else None
        variables["persona_description"] = persona.description if persona.description else None
        variables["persona_expertise"] = persona.expertise if persona.expertise else None

        # Communication style
        if persona.communication_style:
            style = persona.communication_style
            variables["communication_tone"] = style.get("tone")
            variables["communication_formality"] = style.get("formality")
            variables["sentence_endings"] = style.get("sentence_endings", [])
            variables["connectors"] = style.get("connectors", [])
            variables["avoid_words"] = style.get("avoid_words", [])
        else:
            variables["communication_tone"] = None
            variables["communication_formality"] = None
            variables["sentence_endings"] = []
            variables["connectors"] = []
            variables["avoid_words"] = []

        # Perspective
        if persona.perspective:
            perspective = persona.perspective
            variables["perspective_values"] = perspective.get("values", [])
            variables["perspective_biases"] = perspective.get("biases")
            variables["perspective_contrarian"] = perspective.get("contrarian", False)
        else:
            variables["perspective_values"] = []
            variables["perspective_biases"] = None
            variables["perspective_contrarian"] = False

        # Retrieved content
        variables["similar_content"] = (
            [{"text": result.text, "score": result.score} for result in retrieved.similar]
            if retrieved.similar
            else []
        )

        variables["opinions"] = (
            [{"text": result.text, "score": result.score} for result in retrieved.opinions]
            if retrieved.opinions
            else []
        )

        variables["examples"] = (
            [{"text": result.text, "score": result.score} for result in retrieved.examples]
            if retrieved.examples
            else []
        )

        variables["hooks"] = (
            [
                {
                    "text": result.text,
                    "score": result.score,
                    "performance_score": result.performance_score,
                }
                for result in retrieved.hooks
            ]
            if retrieved.hooks
            else []
        )

        # Topic variables
        variables["topic_title"] = topic.title_normalized
        variables["topic_summary"] = topic.summary if topic.summary else None
        variables["topic_terms"] = topic.terms if topic.terms else []
        variables["topic_source_url"] = topic.source_url if topic.source_url else None

        # Generation config
        variables["video_format"] = (
            "YouTube Shorts" if config.format == "shorts" else "long-form video"
        )
        variables["target_duration"] = config.target_duration
        variables["content_style"] = config.style

        # Enriched content (cluster + research)
        enriched = context.enriched
        if enriched:
            variables["enriched_cluster_summary"] = enriched.cluster_summary
            variables["enriched_cluster_sources"] = enriched.cluster_sources
            variables["enriched_research_results"] = [
                {
                    "title": r.title,
                    "content": r.content[:300],  # Truncate for token efficiency
                    "source": r.source,
                }
                for r in enriched.research_results[:5]  # Limit to 5 results
            ]
        else:
            variables["enriched_cluster_summary"] = None
            variables["enriched_cluster_sources"] = []
            variables["enriched_research_results"] = []

        return variables


__all__ = ["PromptBuilder"]
