"""Knowledge Base Search Tool implementation (RAG, CMP-06, CMP-07).

Executes hybrid retrieval combining pgvector dense vector similarity and PostgreSQL
full-text search over knowledge base articles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from src.travelmate.rag.retriever import HybridRetriever
from src.travelmate.clients.embedding_client import EmbeddingClientProtocol
from src.travelmate.infrastructure.database.repositories.base import KbRepositoryProtocol
from src.travelmate.schemas.tools import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    ToolError,
)
from src.travelmate.tools.base import ToolProtocol

logger = structlog.get_logger(__name__)


class KnowledgeSearchTool(ToolProtocol):
    """Tool for searching travel guides and general travel tips.

    Delegates retrieval logic to HybridRetriever to eliminate code duplication
    and maintain Single Responsibility Principle.
    """

    name: str = "knowledge_search"
    description: str = (
        "Search curated travel knowledge base articles, weather guides, seasonal tips, "
        "and destination overviews using hybrid vector + lexical search."
    )

    def __init__(
        self,
        retriever: HybridRetriever | KbRepositoryProtocol | None = None,
        embedding_client: EmbeddingClientProtocol | None = None,
        *,
        kb_repo: KbRepositoryProtocol | None = None,
    ) -> None:
        """Initialize tool with injected HybridRetriever service or repository protocols.

        Supports direct injection of HybridRetriever or dependency protocols
        (KbRepositoryProtocol, EmbeddingClientProtocol) adhering to DIP.

        Args:
            retriever: HybridRetriever instance or KbRepositoryProtocol.
            embedding_client: Optional client implementing EmbeddingClientProtocol.
            kb_repo: Optional repository implementing KbRepositoryProtocol.

        Raises:
            ValueError: If neither a valid retriever nor repository and embedding client are provided.
        """
        if retriever is not None and hasattr(retriever, "retrieve"):
            self._retriever = retriever
        elif (
            isinstance(retriever, KbRepositoryProtocol) or kb_repo is not None
        ) and embedding_client is not None:
            from src.travelmate.rag.retriever import HybridRetriever

            repo = kb_repo if kb_repo is not None else retriever
            self._retriever = HybridRetriever(
                kb_repo=repo,  # type: ignore[arg-type]
                embedding_client=embedding_client,
            )
        elif retriever is not None:
            self._retriever = retriever
        else:
            raise ValueError(
                "KnowledgeSearchTool requires either a retriever instance or "
                "(kb_repo, embedding_client) protocols."
            )

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute hybrid search using query string.

        Args:
            params: Dictionary containing 'query', optional 'category', 'location'.

        Returns:
            KnowledgeSearchResponse dictionary with status 'OK', 'EMPTY', or 'ERROR'.
        """
        try:
            req = KnowledgeSearchRequest.model_validate(params)
        except Exception as exc:
            return KnowledgeSearchResponse(
                status="ERROR",
                error=ToolError(code="ERR-PARAM-01", message=str(exc)),
            ).model_dump()

        try:
            chunks = await self._retriever.retrieve(
                query=req.query,
                category=req.category,
                location=req.location,
                top_k=req.top_k,
            )

            if not chunks:
                return KnowledgeSearchResponse(status="EMPTY", chunks=[]).model_dump()

            return KnowledgeSearchResponse(status="OK", chunks=chunks).model_dump()

        except Exception as exc:
            logger.error("knowledge_search execution error", error=str(exc))
            return KnowledgeSearchResponse(
                status="ERROR",
                error=ToolError(code="ERR-RAG-01", message=str(exc)),
            ).model_dump()
