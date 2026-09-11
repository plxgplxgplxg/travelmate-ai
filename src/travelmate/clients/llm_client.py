"""LLM Client Abstraction Layer (CMP-04, CMP-05, CMP-09).

Encapsulates external LLM provider SDKs (OpenAI-compatible / DeepSeek-V3) behind
a decoupled protocol supporting structured outputs, streaming, and error normalization.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable
from openai import AsyncOpenAI
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


class LLMClientError(Exception):
    """Raised when an external LLM call fails after retries."""


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Structural interface for LLM completion and streaming services."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """Send chat completion request to LLM.

        Args:
            messages: List of message dictionaries containing 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion.
            json_mode: When True, enforces JSON object response format.

        Returns:
            Generated text content string.

        Raises:
            LLMClientError: On unrecoverable API error.
        """
        ...

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream token chunks as they arrive from LLM provider.

        Args:
            messages: List of message dictionaries.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion.

        Yields:
            Token text chunks.
        """
        ...


class OpenAILLMClient(LLMClientProtocol):
    """OpenAI-compatible LLM client adapter for DeepSeek-V3."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the client.

        Args:
            api_key: API secret key. Defaults to settings.openai_api_key.
            base_url: API endpoint URL. Defaults to settings.openai_api_base.
            model: Model name identifier. Defaults to settings.llm_model.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key or settings.openai_api_key or "dummy_dev_key"
        self.base_url = base_url or settings.openai_api_base
        self.model = model or settings.llm_model
        self.timeout = timeout
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """Execute chat completion with automatic retries on transient errors."""
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens or settings.llm_max_tokens
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("LLM completion request failed", model=self.model, error=str(exc))
            raise LLMClientError(f"LLM request error: {exc}") from exc

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream token chunks asynchronously."""
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens or settings.llm_max_tokens

        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
        except Exception as exc:
            logger.error("LLM streaming request failed", model=self.model, error=str(exc))
            raise LLMClientError(f"LLM streaming error: {exc}") from exc
