"""Hugging Face Serverless Inference API embedding client.

Implements EmbeddingClientProtocol with dual-key rotation and automatic
E5 prefix formatting ('passage: ' and 'query: ').
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx
import structlog

from src.travelmate.clients.base import (
    EmbeddingClientProtocol,
    EmbeddingRateLimitError,
    EmbeddingServiceError,
)
from src.travelmate.clients.hf_rotator import HFKeyRotator
from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


class HuggingFaceEmbeddingClient(EmbeddingClientProtocol):
    """Hugging Face Serverless Inference API client with dual-key rotation."""

    def __init__(
        self,
        api_keys: Sequence[str] | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        """Initialize the Hugging Face embedding client.

        Args:
            api_keys: Optional list of API keys. Defaults to settings.hf_api_keys.
            model_name: Embedding model identifier. Defaults to settings.embedding_model.
            timeout: HTTP request timeout in seconds.
            cooldown_seconds: Key cooldown period after HTTP 429.
        """
        keys = api_keys if api_keys is not None else settings.hf_api_keys
        valid_keys = [k for k in keys if k] or ["hf_dummy_test_key"]
        self.model_name = model_name or settings.embedding_model
        self.endpoint_url = (
            f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model_name}"
        )
        cooldown = (
            cooldown_seconds
            if cooldown_seconds is not None
            else settings.hf_rotation_cooldown_seconds
        )
        self.rotator = HFKeyRotator(valid_keys, default_cooldown_seconds=cooldown)
        self.client = httpx.AsyncClient(timeout=timeout or settings.hf_request_timeout_seconds)

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Send embedding request with key rotation and rate limit retry."""
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
                    raise EmbeddingServiceError(
                        f"Unexpected response format from HF API: {type(data)}"
                    )

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
        """Embed a list of knowledge base document chunks with 'passage: ' prefix.

        Args:
            documents: List of chunk texts to embed.

        Returns:
            List of 768d float embedding vectors.
        """
        if not documents:
            return []
        prefixed = [f"passage: {doc}" for doc in documents]
        return await self._embed_with_retry(prefixed)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single search query with 'query: ' prefix.

        Args:
            query: Search query text.

        Returns:
            768d float embedding vector.
        """
        prefixed = [f"query: {query}"]
        vectors = await self._embed_with_retry(prefixed)
        return vectors[0]
