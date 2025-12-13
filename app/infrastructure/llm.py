"""LLM client abstraction using LiteLLM.

This module provides a unified interface for LLM calls across different providers
(Anthropic, OpenAI, etc.) using LiteLLM as the backend.

Benefits:
- Provider-agnostic interface
- Easy model switching via config
- Built-in retry and fallback support
- Consistent response format
"""

from dataclasses import dataclass
from typing import Any

import litellm
from litellm import acompletion

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Configure LiteLLM
litellm.drop_params = True  # Drop unsupported params for each provider


@dataclass
class LLMConfig:
    """LLM configuration for a specific use case.

    Attributes:
        model: Model identifier (e.g., "anthropic/claude-3-5-haiku-20241022")
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0-1)
        timeout: Request timeout in seconds
    """

    model: str
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 60


@dataclass
class LLMResponse:
    """Standardized LLM response.

    Attributes:
        content: Generated text content
        model: Model used for generation
        usage: Token usage statistics
        raw_response: Raw response from provider
    """

    content: str
    model: str
    usage: dict[str, int]
    raw_response: Any = None


class LLMClient:
    """Unified LLM client using LiteLLM.

    Provides a consistent interface for all LLM calls in the application.
    Supports multiple providers through LiteLLM's unified API.

    Model naming convention:
        - Anthropic: "anthropic/claude-3-5-sonnet-20241022"
        - OpenAI: "openai/gpt-4o"
        - Gemini: "gemini/gemini-1.5-pro"

    Example:
        >>> client = LLMClient()
        >>> response = await client.complete(
        ...     config=LLMConfig(model="anthropic/claude-3-5-haiku-20241022"),
        ...     messages=[{"role": "user", "content": "Hello!"}]
        ... )
        >>> print(response.content)
    """

    def __init__(self) -> None:
        """Initialize LLM client with API keys from settings."""
        # Set API keys for providers
        if settings.anthropic_api_key:
            litellm.api_key = settings.anthropic_api_key
        if settings.openai_api_key:
            litellm.openai_key = settings.openai_api_key

        logger.info("LLMClient initialized")

    async def complete(
        self,
        config: LLMConfig,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion from LLM.

        Args:
            config: LLM configuration
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters passed to the model

        Returns:
            LLMResponse with generated content

        Raises:
            LLMError: If generation fails
        """
        try:
            logger.debug(
                "LLM request",
                model=config.model,
                max_tokens=config.max_tokens,
                message_count=len(messages),
            )

            response = await acompletion(
                model=config.model,
                messages=messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                timeout=config.timeout,
                **kwargs,
            )

            # Extract content from response
            content = response.choices[0].message.content or ""

            # Build usage dict
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                    "total_tokens": response.usage.total_tokens or 0,
                }

            logger.debug(
                "LLM response",
                model=response.model,
                content_length=len(content),
                usage=usage,
            )

            return LLMResponse(
                content=content,
                model=response.model or config.model,
                usage=usage,
                raw_response=response,
            )

        except Exception as e:
            logger.error(
                "LLM request failed",
                model=config.model,
                error=str(e),
                exc_info=True,
            )
            raise LLMError(f"LLM request failed: {e}") from e

    async def complete_simple(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Simplified completion for single-turn requests.

        Args:
            model: Model identifier
            prompt: User prompt
            max_tokens: Max tokens
            temperature: Sampling temperature

        Returns:
            Generated text content
        """
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response = await self.complete(
            config=config,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content


class LLMError(Exception):
    """LLM operation failed."""

    pass


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get singleton LLMClient instance.

    Returns:
        LLMClient instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


__all__ = [
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    "LLMError",
    "get_llm_client",
]
