"""Redis-backed session store for multi-turn conversational context state (CMP-03).

Provides atomic serialization, deserialization, and TTL refresh for ContextState
stored at key pattern ctx:{session_id}.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import structlog
from redis.asyncio import Redis

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Structural interface for conversation session state persistence."""

    async def get_context(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve stored context dictionary for a session.

        Args:
            session_id: Unique conversation identifier.

        Returns:
            Context dictionary if found, None otherwise.
        """
        ...

    async def save_context(
        self,
        session_id: str,
        context_data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Persist or update context dictionary with TTL expiration.

        Args:
            session_id: Unique conversation identifier.
            context_data: State payload to serialize and store.
            ttl_seconds: Expiry TTL in seconds.
        """
        ...

    async def clear_context(self, session_id: str) -> None:
        """Delete stored context state for a session.

        Args:
            session_id: Unique conversation identifier.
        """
        ...


class SessionStore(SessionStoreProtocol):
    """Redis adapter implementing SessionStoreProtocol."""

    def __init__(self, redis_client: Redis, default_ttl: int | None = None) -> None:
        """Initialize the session store.

        Args:
            redis_client: Async Redis client connection.
            default_ttl: Expiration duration in seconds (default: settings.redis_session_ttl).
        """
        self._redis = redis_client
        self._default_ttl = default_ttl or settings.redis_session_ttl

    def _format_key(self, session_id: str) -> str:
        """Construct namespaced Redis key for session context."""
        return f"ctx:{session_id.strip()}"

    async def get_context(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve and deserialize stored context state from Redis.

        Args:
            session_id: Unique conversation identifier.

        Returns:
            Deserialized dictionary or None if key expired or not found.
        """
        key = self._format_key(session_id)
        raw_val = await self._redis.get(key)
        if not raw_val:
            return None

        try:
            return json.loads(raw_val)
        except Exception as exc:
            logger.error(
                "Failed to deserialize session context", session_id=session_id, error=str(exc)
            )
            return None

    async def save_context(
        self,
        session_id: str,
        context_data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Serialize and persist context state to Redis with TTL.

        Args:
            session_id: Unique conversation identifier.
            context_data: Dictionary representing context state.
            ttl_seconds: Expiration TTL in seconds (defaults to configured TTL).
        """
        key = self._format_key(session_id)
        ttl = ttl_seconds or self._default_ttl
        payload = json.dumps(context_data, ensure_ascii=False)
        await self._redis.set(key, payload, ex=ttl)
        logger.debug("Saved session context to Redis", session_id=session_id, ttl=ttl)

    async def clear_context(self, session_id: str) -> None:
        """Evict context state from Redis.

        Args:
            session_id: Unique conversation identifier.
        """
        key = self._format_key(session_id)
        await self._redis.delete(key)
        logger.info("Cleared session context from Redis", session_id=session_id)
