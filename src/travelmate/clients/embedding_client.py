"""Embedding Client Abstraction Layer (RAG, CMP-06, CMP-07).

Encapsulates external embedding providers (Hugging Face Serverless Inference API)
behind a decoupled protocol with automatic dual-key rotation and E5 prefix formatting.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol, Sequence, runtime_checkable
import httpx
import structlog

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


class EmbeddingRateLimitError(Exception):
    """Raised when all configured Hugging Face API keys exceed rate limits."""


class EmbeddingServiceError(Exception):
    """Raised when the Hugging Face inference API returns an unrecoverable error."""


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


class HFKeyRotator:
    """Thread-safe and async-safe API key rotator with cooldown tracking."""

    def __init__(self, keys: Sequence[str], default_cooldown_seconds: float = 60.0) -> None:
        if not keys:
            raise ValueError("At least one Hugging Face API key must be provided.")
        self._keys = [k.strip() for k in keys if k.strip()]
        if not self._keys:
            raise ValueError("No valid non-empty Hugging Face API keys found.")
        self._cooldown_seconds = default_cooldown_seconds
        self._cooldown_until: dict[str, float] = {k: 0.0 for k in self._keys}
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    async def get_active_key(self) -> str:
        """Get the currently active API key that is not in cooldown."""
        async with self._lock:
            now = time.monotonic()
            key = self._keys[self._current_index]
            if self._cooldown_until[key] <= now:
                return key

            for idx, candidate in enumerate(self._keys):
                if self._cooldown_until[candidate] <= now:
                    self._current_index = idx
                    logger.info("Switched to active HF API key", key_index=idx)
                    return candidate

            min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
            raise EmbeddingRateLimitError(
                f"All {len(self._keys)} HF API keys are rate-limited. "
                f"Earliest cooldown reset in {min_remaining:.1f}s."
            )

    async def mark_rate_limited(self, key: str, custom_cooldown: float | None = None) -> str:
        """Mark a key as rate-limited (HTTP 429) and advance to the next key."""
        async with self._lock:
            cooldown = custom_cooldown or self._cooldown_seconds
            self._cooldown_until[key] = time.monotonic() + cooldown
            logger.warning(
                "HF API key rate-limited, cooling down",
                masked_key=f"{key[:6]}...{key[-4:]}" if len(key) >= 10 else "***",
                cooldown_seconds=cooldown,
            )

            self._current_index = (self._current_index + 1) % len(self._keys)
            next_key = self._keys[self._current_index]

            now = time.monotonic()
            if self._cooldown_until[next_key] > now:
                for idx, candidate in enumerate(self._keys):
                    if self._cooldown_until[candidate] <= now:
                        self._current_index = idx
                        return candidate

                min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
                raise EmbeddingRateLimitError(
                    f"All {len(self._keys)} HF API keys exhausted after rotation. "
                    f"Cooldown reset in {min_remaining:.1f}s."
                )

            return next_key


class HuggingFaceEmbeddingClient(EmbeddingClientProtocol):
    """Hugging Face Serverless Inference API client with dual-key rotation."""

    def __init__(
        self,
        api_keys: Sequence[str] | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        keys = api_keys if api_keys is not None else settings.hf_api_keys
        valid_keys = [k for k in keys if k] or ["hf_dummy_test_key"]
        self.model_name = model_name or settings.embedding_model
        self.endpoint_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model_name}"
        cooldown = cooldown_seconds if cooldown_seconds is not None else settings.hf_rotation_cooldown_seconds
        self.rotator = HFKeyRotator(valid_keys, default_cooldown_seconds=cooldown)
        self.client = httpx.AsyncClient(timeout=timeout or settings.hf_request_timeout_seconds)

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        max_attempts = len(self.rotator._keys) * 2
        for attempt in range(max_attempts):
            key = await self.rotator.get_active_key()
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": texts,
                "options": {"wait_for_model": True},
            }

            try:
                response = await self.client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data and isinstance(data[0], list):
                        return data
                    elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
                        return [data]
                    raise EmbeddingServiceError(f"Unexpected response format from HF API: {type(data)}")

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    cd = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
                    await self.rotator.mark_rate_limited(key, custom_cooldown=cd)
                    continue

                if response.status_code == 503:
                    logger.info("HF model is loading (cold start), waiting 5 seconds...")
                    await asyncio.sleep(5.0)
                    continue

                raise EmbeddingServiceError(
                    f"HF Inference API returned HTTP {response.status_code}: {response.text}"
                )

            except httpx.RequestError as exc:
                logger.error("HTTP request error to HF API", error=str(exc))
                if attempt == max_attempts - 1:
                    raise EmbeddingServiceError(f"HF API request failed: {exc}") from exc
                await asyncio.sleep(1.0)

        raise EmbeddingRateLimitError("Exceeded maximum retry attempts across all API keys.")

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of knowledge base document chunks with 'passage: ' prefix."""
        if not documents:
            return []
        prefixed = [f"passage: {doc}" for doc in documents]
        return await self._embed_with_retry(prefixed)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single search query with 'query: ' prefix."""
        prefixed = [f"query: {query}"]
        vectors = await self._embed_with_retry(prefixed)
        return vectors[0]
