"""Async Redis connection pool and client lifecycle management.

Provides connection pooling, health checks, and lifecycle teardown using redis.asyncio.
"""

from __future__ import annotations

import redis.asyncio as aioredis
import structlog
from redis.asyncio import Redis

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Retrieve the global active Redis client instance.

    Returns:
        The initialized Redis client.

    Raises:
        RuntimeError: If Redis client has not been initialized via init_redis().
    """
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized. Call init_redis() first.")
    return _redis_client


async def init_redis(redis_url: str | None = None) -> Redis:
    """Initialize the asynchronous Redis connection pool.

    Args:
        redis_url: Optional Redis connection URL. Defaults to settings.redis_url.

    Returns:
        The initialized Redis client instance.
    """
    global _redis_client

    url = redis_url or settings.redis_url
    _redis_client = aioredis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    logger.info("Initialized Redis async connection pool")
    return _redis_client


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis connection pool")
        await _redis_client.aclose()
        _redis_client = None


async def ping_redis() -> bool:
    """Execute ping command to verify Redis connectivity.

    Returns:
        True if Redis responds with PONG, False otherwise.
    """
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception as exc:
        logger.error("Redis health check ping failed", error=str(exc))
        return False
