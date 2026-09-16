"""Hugging Face API key rotator with cooldown tracking.

Manages active key selection, concurrency locks, and exponential cooldown state
for Serverless Inference API keys to handle HTTP 429 rate limits gracefully.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

import structlog

from src.travelmate.clients.base import EmbeddingRateLimitError

logger = structlog.get_logger(__name__)


class HFKeyRotator:
    """Thread-safe and async-safe API key rotator with cooldown tracking."""

    def __init__(self, keys: Sequence[str], default_cooldown_seconds: float = 60.0) -> None:
        """Initialize the rotator with a sequence of API keys.

        Args:
            keys: List or sequence of Hugging Face API keys.
            default_cooldown_seconds: Cooldown duration in seconds when rate limited.

        Raises:
            ValueError: If no valid non-empty API keys are provided.
        """
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
        """Get the currently active API key that is not in cooldown.

        Returns:
            A valid API key string.

        Raises:
            EmbeddingRateLimitError: If all configured keys are currently in cooldown.
        """
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
        """Mark a key as rate-limited (HTTP 429) and advance to the next available key.

        Args:
            key: The key that triggered the rate limit.
            custom_cooldown: Optional explicit cooldown seconds (from Retry-After header).

        Returns:
            Next available API key string.

        Raises:
            EmbeddingRateLimitError: If all keys are exhausted after rotation.
        """
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
