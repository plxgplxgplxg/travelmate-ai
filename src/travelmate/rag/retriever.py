"""Hybrid Retriever Service for Knowledge Base RAG.

High-level interface encapsulating query embedding and Reciprocal Rank Fusion
search over PostgreSQL pgvector.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import structlog

from src.travelmate.clients.base import EmbeddingClientProtocol
from src.travelmate.infrastructure.database.repositories.base import KbRepositoryProtocol
from src.travelmate.schemas.tools import KnowledgeChunkItem

logger = structlog.get_logger(__name__)


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Structural interface for knowledge retrieval services.

    Consumers (e.g. KnowledgeSearchTool) depend on this Protocol
    rather than the concrete HybridRetriever, adhering to DIP (Rule 3).
    """

    async def retrieve(
        self,
        query: str,
        category: str | None = None,
        location: str | None = None,
        top_k: int = 3,
    ) -> list[KnowledgeChunkItem]:
        """Retrieve most relevant knowledge chunks.

        Args:
            query: User question or search topic.
            category: Optional category filter.
            location: Optional destination location filter.
            top_k: Maximum chunk count to return.

        Returns:
            List of ranked KnowledgeChunkItem instances.
        """
        ...


class HybridRetriever:
    """Service orchestrating dense vector generation and hybrid DB retrieval."""

    def __init__(
        self,
        kb_repo: KbRepositoryProtocol,
        embedding_client: EmbeddingClientProtocol,
    ) -> None:
        """Initialize the retriever service.

        Args:
            kb_repo: Repository implementing KbRepositoryProtocol.
            embedding_client: Client implementing EmbeddingClientProtocol.
        """
        self._repo = kb_repo
        self._embedding_client = embedding_client

    async def retrieve(
        self,
        query: str,
        category: str | None = None,
        location: str | None = None,
        top_k: int = 3,
    ) -> list[KnowledgeChunkItem]:
        """Retrieve most relevant knowledge chunks using hybrid RRF scoring.

        Args:
            query: User question or search topic.
            category: Optional category filter.
            location: Optional destination location filter.
            top_k: Maximum chunk count to return.

        Returns:
            List of ranked KnowledgeChunkItem instances.
        """
        query_vector = await self._embedding_client.embed_query(query)
        ranked_hits = await self._repo.hybrid_search(
            query_text=query,
            query_vector=query_vector,
            category_filter=category,
            location_filter=location,
            limit=top_k,
        )

        return [
            KnowledgeChunkItem(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                title=chunk.title,
                content=chunk.content,
                score=score,
                source_url=chunk.source_url,
                source_type=chunk.source_type,
                last_updated=str(chunk.last_updated) if chunk.last_updated else None,
                scope_and_limitations=chunk.scope_and_limitations,
            )
            for chunk, score in ranked_hits
        ]
