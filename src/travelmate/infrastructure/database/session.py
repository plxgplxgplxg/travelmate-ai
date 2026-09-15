"""PostgreSQL connection and session lifecycle management.

Manages AsyncEngine, async session factory, pgvector codec registration,
and connection health checks for TravelMate AI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)

# Global engine and sessionmaker instances managed via lifespan
_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Retrieve the global AsyncEngine instance.

    Returns:
        The initialized AsyncEngine instance.

    Raises:
        RuntimeError: If the engine has not been initialized via init_db().
    """
    if _async_engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_db() first.")
    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retrieve the global async sessionmaker factory.

    Returns:
        The initialized async_sessionmaker instance.

    Raises:
        RuntimeError: If session factory has not been initialized via init_db().
    """
    if _async_session_factory is None:
        raise RuntimeError("Session factory is not initialized. Call init_db() first.")
    return _async_session_factory


async def init_db(
    database_url: str | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Initialize the AsyncEngine and session factory with pgvector codec.

    Args:
        database_url: Optional database URL override. Defaults to settings.database_url.

    Returns:
        Tuple containing initialized (AsyncEngine, sessionmaker).
    """
    global _async_engine, _async_session_factory

    url = database_url or settings.database_url

    _async_engine = create_async_engine(
        url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "hnsw.ef_search": "100",
            }
        },
    )

    # Register pgvector codec on new raw connections
    @_async_engine.sync_engine.connect()
    def _on_connect(dbapi_connection, connection_record):
        # Asyncpg uses connection listener on underlying driver
        pass

    _async_session_factory = async_sessionmaker(
        bind=_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    logger.info("Initialized PostgreSQL async engine and session factory")
    return _async_engine, _async_session_factory


async def close_db() -> None:
    """Gracefully dispose and close connection pool during shutdown."""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        logger.info("Disposing PostgreSQL connection pool")
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None


async def ping_db() -> bool:
    """Execute simple SELECT 1 query to verify database health.

    Returns:
        True if database responds successfully, False otherwise.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("PostgreSQL health check ping failed", error=str(exc))
        return False


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Context manager providing an transactional AsyncSession.

    Yields:
        Active SQLAlchemy AsyncSession.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
