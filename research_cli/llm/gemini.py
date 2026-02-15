"""Google Gemini LLM provider implementation."""

import warnings
from typing import AsyncIterator, Optional

# Suppress FutureWarning from deprecated google.generativeai package on import
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai

from .base import BaseLLM, LLMResponse, retry_llm_call


class GeminiLLM(BaseLLM):
    """Google Gemini provider.

    Supports Gemini 3.x and 2.x models.
    Uses the official Google Generative AI Python SDK.
    """

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        """Initialize Gemini client.

        Args:
            api_key: Google API key
            model: Gemini model ID (default: Gemini 3 Flash)
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

        # Gemini thinking models consume thinking tokens from max_output_tokens
        # Use higher limit to avoid truncation (thinking tokens typically 8x output)
        effective_max_tokens = max_tokens
        if any(v in self.model for v in ("2.5", "3-pro", "3-flash")):
            effective_max_tokens = max(max_tokens * 8, 8192)

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=effective_max_tokens,
            **kwargs
        )

        async def _call():
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
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        effective_max_tokens = max_tokens
        if "2.5" in self.model:
            effective_max_tokens = max(max_tokens * 8, 8192)

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=effective_max_tokens,
            **kwargs
        )

        async def _call():
            response = await self.client.generate_content_async(
                full_prompt,
                generation_config=generation_config,
                stream=True,
            )

            # Drain the stream to keep connection alive; collect text chunks
            chunks_text = []
            last_chunk = None
            async for chunk in response:
                last_chunk = chunk
                if chunk.text:
                    chunks_text.append(chunk.text)

            content = "".join(chunks_text)

            # Extract token counts and stop reason from the last chunk
            input_tokens = None
            output_tokens = None
            stop_reason = None

            if last_chunk:
                if hasattr(last_chunk, 'usage_metadata') and last_chunk.usage_metadata:
                    input_tokens = last_chunk.usage_metadata.prompt_token_count
                    output_tokens = last_chunk.usage_metadata.candidates_token_count

                if hasattr(last_chunk, 'candidates') and last_chunk.candidates:
                    finish_reason = last_chunk.candidates[0].finish_reason
                    if finish_reason is not None:
                        stop_reason = finish_reason.name if hasattr(finish_reason, 'name') else str(finish_reason)

            return LLMResponse(
                content=content,
                model=self.model,
                provider="google",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=stop_reason,
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

        # Gemini 2.5 thinking models consume thinking tokens from max_output_tokens
        effective_max_tokens = max_tokens
        if "2.5" in self.model:
            effective_max_tokens = max(max_tokens * 8, 8192)

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=effective_max_tokens,
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
