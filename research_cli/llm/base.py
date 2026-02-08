"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Standard response format from any LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    stop_reason: Optional[str] = None  # "end_turn"/"stop" = normal, "max_tokens"/"length" = truncated

    @property
    def total_tokens(self) -> Optional[int]:
        """Total tokens used (input + output)."""
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


class BaseLLM(ABC):
    """Abstract interface for LLM providers.

    All provider implementations must support synchronous generation
    and optional streaming. This allows consistent usage across
    Claude, Gemini, GPT, and future providers.
    """

    def __init__(self, api_key: str, model: str):
        """Initialize LLM provider.

        Args:
            api_key: API authentication key
            model: Model identifier (e.g., "claude-opus-4-5", "gpt-4")
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Generate text completion.

        Args:
            prompt: User prompt/message
            system: System prompt (provider-specific handling)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated content and metadata
        """
        pass

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text completion (optional, can raise NotImplementedError).

        Args:
            prompt: User prompt/message
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Yields:
            Text chunks as they are generated
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'anthropic', 'openai', 'google')."""
        pass
