"""Google Gemini LLM provider implementation."""

from typing import AsyncIterator, Optional
import google.generativeai as genai

from .base import BaseLLM, LLMResponse


class GeminiLLM(BaseLLM):
    """Google Gemini provider.

    Supports Gemini 2.0 Pro and other Gemini models.
    Uses the official Google Generative AI Python SDK.
    """

    def __init__(self, api_key: str, model: str = "gemini-3-flash"):
        """Initialize Gemini client.

        Args:
            api_key: Google API key
            model: Gemini model ID (default: Gemini 2.0 Flash)
        """
        super().__init__(api_key, model)
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(model)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Generate text using Gemini.

        Args:
            prompt: User message
            system: System prompt (prepended to prompt for Gemini)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional Gemini-specific parameters

        Returns:
            LLMResponse with generated content
        """
        # Gemini doesn't have native system prompts, so prepend to user message
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            **kwargs
        )

        response = await self.client.generate_content_async(
            full_prompt,
            generation_config=generation_config,
        )

        # Extract token counts if available
        input_tokens = None
        output_tokens = None
        if hasattr(response, 'usage_metadata'):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count

        # Extract stop reason if available
        stop_reason = None
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = response.candidates[0].finish_reason
            # Gemini uses enum: 1=STOP (normal), 2=MAX_TOKENS, 3=SAFETY, etc.
            if finish_reason is not None:
                stop_reason = finish_reason.name if hasattr(finish_reason, 'name') else str(finish_reason)

        return LLMResponse(
            content=response.text,
            model=self.model,
            provider="google",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
        )

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text generation from Gemini.

        Args:
            prompt: User message
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional parameters

        Yields:
            Text chunks as they arrive
        """
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            **kwargs
        )

        response = await self.client.generate_content_async(
            full_prompt,
            generation_config=generation_config,
            stream=True,
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "google"
