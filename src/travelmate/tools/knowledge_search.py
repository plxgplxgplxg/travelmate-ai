"""Knowledge Base Search Tool implementation (RAG, CMP-06, CMP-07).

Executes hybrid retrieval combining pgvector dense vector similarity and PostgreSQL
full-text search over knowledge base articles.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.travelmate.rag.retriever import RetrieverProtocol
from src.travelmate.schemas.tools import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    ToolError,
)
from src.travelmate.tools.base import ToolProtocol

logger = structlog.get_logger(__name__)


class KnowledgeSearchTool(ToolProtocol):
    """Tool for searching travel guides and general travel tips.

    Delegates retrieval logic to a RetrieverProtocol implementation,
    adhering to Dependency Inversion Principle (Rule 3).
    """

    name: str = "knowledge_search"
    description: str = (
        "Search curated travel knowledge base articles, weather guides, seasonal tips, "
        "and destination overviews using hybrid vector + lexical search."
    )

    def __init__(self, retriever: RetrieverProtocol) -> None:
        """Initialize tool with injected retriever dependency.

        Args:
            retriever: Service implementing RetrieverProtocol for knowledge retrieval.
        """
        self._retriever = retriever

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
