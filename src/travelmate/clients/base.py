"""Client protocol definitions and shared exception types.

Defines structural interfaces for external provider adapters (LLM, Embedding, Tracing)
adhering to the Dependency Inversion Principle (DIP). Consumers depend exclusively
on these protocols rather than concrete vendor SDKs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------
# Embedding Client Protocols & Exceptions
# ---------------------------------------------------------


class EmbeddingClientError(Exception):
    """Base exception for external embedding service failures."""


class EmbeddingRateLimitError(EmbeddingClientError):
    """Raised when all configured embedding API keys exceed rate limits."""


class EmbeddingServiceError(EmbeddingClientError):
    """Raised when the embedding inference service returns an unrecoverable error."""


@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """Structural interface for text embedding providers."""

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of document strings.

        Args:
            documents: List of text content to embed.

        Returns:
            List of float embedding vectors.
        """
        ...

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        Args:
            query: Search query text.

        Returns:
            Float embedding vector.
        """
        ...

    async def close(self) -> None:
        """Release underlying network resources."""
        ...


# ---------------------------------------------------------
# LLM Client Protocols & Exceptions
# ---------------------------------------------------------


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
