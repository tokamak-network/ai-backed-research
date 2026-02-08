"""Anthropic Claude LLM provider implementation."""

from typing import AsyncIterator, Optional
from anthropic import AsyncAnthropic

from .base import BaseLLM, LLMResponse


class ClaudeLLM(BaseLLM):
    """Anthropic Claude provider.

    Supports Claude 3.5 Sonnet, Claude Opus 4.5, and other Claude models.
    Uses the official Anthropic Python SDK.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4.5", base_url: Optional[str] = None):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key
            model: Claude model ID (default: Sonnet 4)
            base_url: Optional custom base URL for Anthropic API
        """
        super().__init__(api_key, model)
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncAnthropic(**client_kwargs)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Generate text using Claude.

        Args:
            prompt: User message
            system: System prompt (Claude supports native system prompts)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional Claude-specific parameters

        Returns:
            LLMResponse with generated content
        """
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            messages=messages,
            system=system if system else None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            provider="anthropic",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    async def generate_streaming(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Generate text using streaming to prevent proxy idle-connection timeouts.

        Behaves identically to generate() but uses the streaming API internally,
        keeping the HTTP connection alive with incremental chunks.  Returns the
        same LLMResponse once the full message has been received.
        """
        messages = [{"role": "user", "content": prompt}]

        async with self.client.messages.stream(
            model=self.model,
            messages=messages,
            system=system if system else None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ) as stream:
            async for _chunk in stream.text_stream:
                pass  # drain the stream to keep connection alive
            message = await stream.get_final_message()

        return LLMResponse(
            content=message.content[0].text,
            model=message.model,
            provider="anthropic",
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason,
        )

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text generation from Claude.

        Args:
            prompt: User message
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional parameters

        Yields:
            Text chunks as they arrive
        """
        messages = [{"role": "user", "content": prompt}]

        async with self.client.messages.stream(
            model=self.model,
            messages=messages,
            system=system if system else None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "anthropic"
