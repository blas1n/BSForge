"""Content characteristic classification using LLM.

This module provides LLM-based classification for content chunks when
pattern-based classification is insufficient.
"""

from app.core.config import get_config
from app.core.logging import get_logger
from app.infrastructure.llm import LLMClient, LLMConfig
from app.prompts.manager import PromptType, get_prompt_manager

logger = get_logger(__name__)


class ContentClassifier:
    """LLM-based content characteristic classifier.

    Provides more accurate classification than pattern matching,
    but with higher cost and latency. Uses centralized prompt templates
    from prompts/templates/.

    Attributes:
        llm_client: LLMClient for unified LLM access
        model: Model to use (default: llm_model_light from settings)
        prompt_manager: PromptManager for template rendering
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str | None = None,
    ):
        """Initialize ContentClassifier.

        Args:
            llm_client: LLMClient instance
            model: Model name in LiteLLM format (default: from settings)
        """
        self.llm_client = llm_client
        self.model = model or get_config().llm_model_light
        self.prompt_manager = get_prompt_manager()

    async def classify_characteristics(self, text: str) -> dict[str, bool]:
        """Classify content characteristics using LLM.

        Args:
            text: Text to classify

        Returns:
            Dict with is_opinion, is_example, is_analogy
        """
        # Render prompt from template
        prompt = self.prompt_manager.render(
            PromptType.CONTENT_CLASSIFICATION,
            text=text,
        )

        try:
            config = LLMConfig(
                model=self.model,
                max_tokens=50,
                temperature=0.0,  # Deterministic for classification
            )

            response = await self.llm_client.complete(
                config=config,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content.strip().lower()

            # Parse response
            is_opinion = "opinion: yes" in result_text
            is_example = "example: yes" in result_text
            is_analogy = "analogy: yes" in result_text

            logger.debug(
                f"LLM classification: opinion={is_opinion}, "
                f"example={is_example}, analogy={is_analogy}"
            )

            return {
                "is_opinion": is_opinion,
                "is_example": is_example,
                "is_analogy": is_analogy,
            }

        except Exception as e:
            logger.warning(
                f"LLM classification failed, falling back to False: {e}",
                exc_info=True,
            )
            return {
                "is_opinion": False,
                "is_example": False,
                "is_analogy": False,
            }

    async def classify_batch(self, texts: list[str]) -> list[dict[str, bool]]:
        """Classify multiple texts in batch.

        Note: Currently processes sequentially. For production,
        consider parallel processing with rate limiting.

        Args:
            texts: List of texts to classify

        Returns:
            List of classification results
        """
        results = []
        for text in texts:
            result = await self.classify_characteristics(text)
            results.append(result)
        return results


__all__ = ["ContentClassifier"]
