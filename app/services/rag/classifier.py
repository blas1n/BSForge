"""Content characteristic classification using LLM.

This module provides LLM-based classification for content chunks when
pattern-based classification is insufficient.
"""

from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic

from app.core.logging import get_logger
from app.prompts.manager import PromptType, get_prompt_manager

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ContentClassifier:
    """LLM-based content characteristic classifier.

    Provides more accurate classification than pattern matching,
    but with higher cost and latency. Uses centralized prompt templates
    from prompts/templates/.

    Attributes:
        llm_client: Anthropic client for LLM calls
        model: Model to use (default: Haiku for cost efficiency)
        prompt_manager: PromptManager for template rendering
    """

    def __init__(
        self,
        llm_client: AsyncAnthropic,
        model: str = "claude-3-5-haiku-20241022",
    ):
        """Initialize ContentClassifier.

        Args:
            llm_client: Anthropic client
            model: Model name (default: Haiku)
        """
        self.llm_client = llm_client
        self.model = model
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
            response = await self.llm_client.messages.create(
                model=self.model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from response (handle union types)
            content_block = response.content[0]
            if not hasattr(content_block, "text"):
                raise ValueError(f"Unexpected content type: {type(content_block)}")

            result_text = content_block.text.strip().lower()

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
