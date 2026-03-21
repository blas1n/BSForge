"""LLM client abstraction using LiteLLM.

This module provides a unified interface for LLM calls through a single
LLM gateway (e.g., Ollama, OpenAI-compatible endpoint) using LiteLLM as the backend.

Benefits:
- Single gateway configuration (base_url + api_key + model)
- Easy model switching via config
- Built-in retry and fallback support
- Consistent response format
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import litellm
from litellm import ModelResponse, acompletion

from app.core.exceptions import ServiceError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.prompts.manager import LLMSettings

logger = get_logger(__name__)

# Configure LiteLLM
litellm.drop_params = True  # Drop unsupported params for each provider

# Known LiteLLM provider prefixes — models with these don't need re-prefixing
_KNOWN_PROVIDER_PREFIXES = ("openai/", "anthropic/", "azure/", "bedrock/", "ollama/")


@dataclass
class LLMConfig:
    """LLM configuration for a specific use case.

    Attributes:
        model: Model identifier (e.g., "anthropic/claude-haiku-4-5-20251001")
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0-1)
        timeout: Request timeout in seconds
    """

    model: str
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 60

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

    @classmethod
    def from_prompt_settings(cls, llm_settings: "LLMSettings", timeout: int = 60) -> "LLMConfig":
        """Create LLMConfig from prompt template LLMSettings.

        Args:
            llm_settings: Settings from prompt template
            timeout: Request timeout in seconds (default 60)

        Returns:
            LLMConfig instance
        """
        return cls(
            model=llm_settings.model,
            max_tokens=llm_settings.max_tokens,
            temperature=llm_settings.temperature,
            timeout=timeout,
        )


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
    """Unified LLM client using LiteLLM with a single gateway.

    Routes all LLM calls through a configured base URL with a single API key.

    Example:
        >>> client = LLMClient(
        ...     base_url="https://api.anthropic.com/v1",
        ...     api_key="sk-...",
        ...     default_model="anthropic/claude-sonnet-4-20250514",
        ... )
        >>> response = await client.complete(
        ...     config=LLMConfig(model="anthropic/claude-sonnet-4-20250514"),
        ...     messages=[{"role": "user", "content": "Hello!"}]
        ... )
        >>> print(response.content)
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        default_model: str = "",
    ) -> None:
        """Initialize LLM client with gateway settings.

        Args:
            base_url: LLM gateway base URL
            api_key: API key for the gateway
            default_model: Default model to use when not specified in config
        """
        self.base_url = base_url
        self.api_key = api_key
        self.default_model = default_model

        logger.info("LLMClient initialized", base_url=base_url)

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
        model = config.model or self.default_model
        try:
            # When using a proxy (api_base), LiteLLM needs a provider prefix
            # to route correctly. Only add if model has no provider prefix yet.
            if self.base_url and model and not model.startswith(_KNOWN_PROVIDER_PREFIXES):
                logger.debug("auto_prefixed_model", original=model, prefixed=f"openai/{model}")
                model = f"openai/{model}"

            logger.debug(
                "LLM request",
                model=model,
                max_tokens=config.max_tokens,
                message_count=len(messages),
            )

            response = cast(
                ModelResponse,
                await acompletion(
                    model=model,
                    messages=messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    timeout=config.timeout,
                    api_base=self.base_url or None,
                    api_key=self.api_key or None,
                    **kwargs,
                ),
            )

            # Extract content from response
            if not response.choices:
                raise LLMError("LLM response contains no choices")
            choice = response.choices[0]
            message = getattr(choice, "message", None)
            if message is None:
                raise LLMError("LLM response choice has no message")
            content = message.content or ""

            # Build usage dict (usage is dynamically set, not a declared field)
            usage = {}
            response_usage = getattr(response, "usage", None)
            if response_usage:
                usage = {
                    "prompt_tokens": response_usage.prompt_tokens or 0,
                    "completion_tokens": response_usage.completion_tokens or 0,
                    "total_tokens": response_usage.total_tokens or 0,
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

        except (litellm.exceptions.APIError, litellm.exceptions.Timeout) as e:
            logger.error(
                "LLM API error",
                model=model,
                error=str(e),
            )
            raise LLMError(f"LLM API error: {e}") from e
        except Exception as e:
            logger.error(
                "LLM request failed",
                model=model,
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


class LLMError(ServiceError):
    """LLM operation failed."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message, service_name="llm", context=context)


__all__ = [
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    "LLMError",
]
