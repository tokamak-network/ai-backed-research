"""OpenAI GPT LLM provider implementation."""

from typing import AsyncIterator, Optional
from openai import AsyncOpenAI

from .base import BaseLLM, LLMResponse, retry_llm_call


class OpenAILLM(BaseLLM):
    """OpenAI GPT provider.

    Supports GPT-4, GPT-4 Turbo, and other OpenAI models.
    Uses the official OpenAI Python SDK.
    """

    def __init__(self, api_key: str, model: str = "gpt-5.2-pro", base_url: Optional[str] = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: GPT model ID (default: GPT-4 Turbo)
            base_url: Optional custom base URL (e.g. OpenRouter)
        """
        super().__init__(api_key, model)
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Generate text using OpenAI GPT.

        Args:
            prompt: User message
            system: System prompt (OpenAI supports native system messages)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional OpenAI-specific parameters

        Returns:
            LLMResponse with generated content
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # gpt-5 models only support temperature=1
        api_temp = 1.0 if "gpt-5" in self.model else temperature

        # Support json_mode: OpenAI uses response_format
        json_mode = kwargs.pop("json_mode", False)
        if json_mode:
            kwargs.setdefault("response_format", {"type": "json_object"})

        async def _call():
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=api_temp,
                max_tokens=max_tokens,
                **kwargs
            )
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                provider="openai",
                input_tokens=response.usage.prompt_tokens if response.usage else None,
                output_tokens=response.usage.completion_tokens if response.usage else None,
                stop_reason=response.choices[0].finish_reason,
            )

        return await retry_llm_call(_call)

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
        keeping the HTTP connection alive with incremental chunks. Returns the
        same LLMResponse once the full message has been received.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # gpt-5 models only support temperature=1
        api_temp = 1.0 if "gpt-5" in self.model else temperature

        async def _call():
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=api_temp,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs
            )

            full_content = []
            finish_reason = None
            input_tokens = None
            output_tokens = None

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_content.append(chunk.choices[0].delta.content)

                if chunk.choices and chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

                if hasattr(chunk, "usage") and chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens
                    output_tokens = chunk.usage.completion_tokens

            return LLMResponse(
                content="".join(full_content),
                model=self.model,
                provider="openai",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=finish_reason,
            )

        return await retry_llm_call(_call)

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text generation from OpenAI.

        Args:
            prompt: User message
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional parameters

        Yields:
            Text chunks as they arrive
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        api_temp = 1.0 if "gpt-5" in self.model else temperature

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=api_temp,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "openai"
