"""FastAPI Dependency Injection providers (DIP seam).

Provides scoped database sessions, repository instances, Redis stores, and external
client adapters to routes and workflow graphs using typing.Annotated and fastapi.Depends.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.travelmate.clients.embedding_client import (
    EmbeddingClientProtocol,
    HuggingFaceEmbeddingClient,
)
from src.travelmate.clients.langfuse_client import (
    TracerClientProtocol,
    get_tracer_client,
)
from src.travelmate.clients.llm_client import (
    LLMClientProtocol,
    OpenAILLMClient,
)
from src.travelmate.infrastructure.database.repositories.kb_repo import KbRepository
from src.travelmate.infrastructure.database.repositories.log_repo import LogRepository
from src.travelmate.infrastructure.database.repositories.poi_repo import PoiRepository
from src.travelmate.infrastructure.database.session import get_db_session
from src.travelmate.infrastructure.redis.cache import CacheManager
from src.travelmate.infrastructure.redis.client import get_redis_client
from src.travelmate.infrastructure.redis.session_store import SessionStore


async def get_db() -> AsyncIterator[AsyncSession]:
    """Provide scoped AsyncSession dependency with auto-rollback on error.

    Yields:
        Active SQLAlchemy AsyncSession.
    """
    async with get_db_session() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_poi_repository(session: DbSessionDep) -> PoiRepository:
    """Provide PoiRepository injected with active DB session."""
    return PoiRepository(session=session)


PoiRepoDep = Annotated[PoiRepository, Depends(get_poi_repository)]


def get_kb_repository(session: DbSessionDep) -> KbRepository:
    """Provide KbRepository injected with active DB session."""
    return KbRepository(session=session)


KbRepoDep = Annotated[KbRepository, Depends(get_kb_repository)]


def get_log_repository(session: DbSessionDep) -> LogRepository:
    """Provide LogRepository injected with active DB session."""
    return LogRepository(session=session)


LogRepoDep = Annotated[LogRepository, Depends(get_log_repository)]


def get_session_store() -> SessionStore:
    """Provide SessionStore injected with global Redis client."""
    redis_client = get_redis_client()
    return SessionStore(redis_client=redis_client)


SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]


def get_cache_manager() -> CacheManager:
    """Provide CacheManager injected with global Redis client."""
    redis_client = get_redis_client()
    return CacheManager(redis_client=redis_client)


CacheManagerDep = Annotated[CacheManager, Depends(get_cache_manager)]


def get_llm_client() -> LLMClientProtocol:
    """Provide LLM client adapter configured with application settings."""
    return OpenAILLMClient()


LLMClientDep = Annotated[LLMClientProtocol, Depends(get_llm_client)]


def get_embedding_client() -> EmbeddingClientProtocol:
    """Provide Hugging Face embedding client adapter."""
    return HuggingFaceEmbeddingClient()


EmbeddingClientDep = Annotated[EmbeddingClientProtocol, Depends(get_embedding_client)]


def get_tracer() -> TracerClientProtocol:
    """Provide observability tracer client."""
    return get_tracer_client()


TracerDep = Annotated[TracerClientProtocol, Depends(get_tracer)]
