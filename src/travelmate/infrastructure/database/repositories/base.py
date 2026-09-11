"""Repository protocol definitions following Dependency Inversion Principle (DIP).

Defines structural interfaces for POI search, Knowledge Base hybrid retrieval,
and conversation logging. Consumers (Tools, Agents, Services) depend on these
Protocols rather than concrete database sessions or drivers.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.travelmate.infrastructure.database.models import (
    ConversationLogModel,
    KbChunkModel,
    PoiModel,
)


@runtime_checkable
class PoiRepositoryProtocol(Protocol):
    """Structural interface for querying point of interest (POI) records."""

    async def search_poi(
        self,
        location: str,
        category: str,
        budget_min: int | None = None,
        budget_max: int | None = None,
        preferences: list[str] | None = None,
        limit: int = 5,
    ) -> list[PoiModel]:
        """Search POI entities using relational filters.

        Args:
            location: Province or city name (e.g., 'Đà Nẵng', 'Hội An').
            category: Domain category (e.g., 'ACCOM', 'FOOD', 'ATTRACTION').
            budget_min: Minimum price filter in VND.
            budget_max: Maximum price filter in VND.
            preferences: Attribute keywords to match against attributes JSONB.
            limit: Maximum number of POI records to return.

        Returns:
            List of matching PoiModel instances.
        """
        ...

    async def get_by_id(self, poi_id: str) -> PoiModel | None:
        """Fetch a specific POI by primary key.

        Args:
            poi_id: Unique POI identifier.

        Returns:
            PoiModel instance if found, None otherwise.
        """
        ...


@runtime_checkable
class KbRepositoryProtocol(Protocol):
    """Structural interface for hybrid knowledge base vector & text search."""

    async def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        category_filter: str | None = None,
        location_filter: str | None = None,
        limit: int = 3,
        rrf_k: int = 60,
    ) -> list[tuple[KbChunkModel, float]]:
        """Perform hybrid dense vector + lexical full-text search with RRF scoring.

        Args:
            query_text: Raw user query string for FTS ranking.
            query_vector: 768d float embedding vector for cosine ANN.
            category_filter: Optional category constraint.
            location_filter: Optional location constraint.
            limit: Maximum ranked chunks to return.
            rrf_k: Smoothing constant for Reciprocal Rank Fusion.

        Returns:
            List of tuples (KbChunkModel, rrf_score) ordered descending by score.
        """
        ...

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Batch upsert knowledge chunks with conflict handling.

        Args:
            chunks: List of chunk data dicts containing chunk_id, embedding, content, etc.

        Returns:
            Number of chunks successfully upserted.
        """
        ...


@runtime_checkable
class LogRepositoryProtocol(Protocol):
    """Structural interface for conversation and audit trace logging."""

    async def log_interaction(
        self,
        session_id: str,
        role: str,
        content: str,
        context_snapshot: dict[str, Any] | None = None,
        intent: str | None = None,
        bot_version: str = "V1.0",
    ) -> None:
        """Record a single interaction turn or agent action.

        Args:
            session_id: Conversation session identifier.
            role: Message sender ('user', 'assistant', 'system').
            content: Raw message text or action summary.
            context_snapshot: Current state snapshot of the conversation.
            intent: Classified intent label if available.
            bot_version: Bot release version tag.
        """
        ...

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[ConversationLogModel]:
        """Fetch chronological interaction history for a given session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of recent log turns.

        Returns:
            List of ConversationLogModel ordered chronologically.
        """
        ...
