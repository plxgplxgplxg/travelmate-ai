"""Concrete repository implementation for Knowledge Base chunks and Hybrid Retrieval.

Combines pgvector cosine distance Approximate Nearest Neighbor (ANN) search with
PostgreSQL Full-Text Search (tsvector), scored and merged via Reciprocal Rank
Fusion (RRF) for robust grounded retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.travelmate.infrastructure.database.models import KbChunkModel
from src.travelmate.infrastructure.database.repositories.base import KbRepositoryProtocol

logger = structlog.get_logger(__name__)


class KbRepository(KbRepositoryProtocol):
    """PostgreSQL + pgvector adapter implementing KbRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active AsyncSession.

        Args:
            session: SQLAlchemy AsyncSession for executing queries.
        """
        self._session = session

    async def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        category_filter: str | None = None,
        location_filter: str | None = None,
        limit: int = 3,
        rrf_k: int = 60,
    ) -> list[tuple[KbChunkModel, float]]:
        """Perform hybrid dense vector + lexical full-text search with RRF and recency scoring.

        Filters strictly by active documents (is_active=True) and applies exponential
        time-decay weighting based on last_updated to prioritize fresh information.

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
        candidate_limit = max(limit * 3, 10)

        # 1. Semantic Vector Search Query (Active chunks only)
        vector_stmt = (
            select(
                KbChunkModel,
                KbChunkModel.embedding.cosine_distance(query_vector).label("distance"),
            )
            .where(KbChunkModel.is_active.is_(True))
        )
        if category_filter:
            vector_stmt = vector_stmt.where(
                func.lower(KbChunkModel.category) == category_filter.strip().lower()
            )
        if location_filter:
            vector_stmt = vector_stmt.where(
                func.lower(KbChunkModel.location).contains(location_filter.strip().lower())
            )
        vector_stmt = vector_stmt.order_by("distance").limit(candidate_limit)

        # 2. Lexical Full-Text Search Query (Active chunks only)
        fts_query = func.plainto_tsquery("simple", query_text)
        lexical_stmt = (
            select(
                KbChunkModel,
                func.ts_rank(
                    func.coalesce(
                        KbChunkModel.content_tsvector,
                        func.to_tsvector("simple", KbChunkModel.content),
                    ),
                    fts_query,
                ).label("rank"),
            )
            .where(KbChunkModel.is_active.is_(True))
            .where(
                func.coalesce(
                    KbChunkModel.content_tsvector,
                    func.to_tsvector("simple", KbChunkModel.content),
                ).op("@@")(fts_query)
            )
        )
        if category_filter:
            lexical_stmt = lexical_stmt.where(
                func.lower(KbChunkModel.category) == category_filter.strip().lower()
            )
        if location_filter:
            lexical_stmt = lexical_stmt.where(
                func.lower(KbChunkModel.location).contains(location_filter.strip().lower())
            )
        lexical_stmt = lexical_stmt.order_by(func.desc("rank")).limit(candidate_limit)

        # Execute searches
        vec_results = (await self._session.execute(vector_stmt)).all()
        try:
            lex_results = (await self._session.execute(lexical_stmt)).all()
        except Exception as exc:
            logger.warning("FTS query failed, relying solely on vector search", error=str(exc))
            lex_results = []

        # 3. Reciprocal Rank Fusion Merge with Recency Time-Decay
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, KbChunkModel] = {}
        today = datetime.now(timezone.utc).date()

        for rank, row in enumerate(vec_results):
            chunk = row[0]
            chunk_id = chunk.chunk_id
            days_diff = max((today - chunk.last_updated).days, 0) if chunk.last_updated else 180
            recency_boost = math.exp(-0.001 * days_diff)
            weighted_rrf = (1.0 / (rrf_k + rank + 1)) * (0.85 + 0.15 * recency_boost)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + weighted_rrf
            chunk_map[chunk_id] = chunk

        for rank, row in enumerate(lex_results):
            chunk = row[0]
            chunk_id = chunk.chunk_id
            days_diff = max((today - chunk.last_updated).days, 0) if chunk.last_updated else 180
            recency_boost = math.exp(-0.001 * days_diff)
            weighted_rrf = (1.0 / (rrf_k + rank + 1)) * (0.85 + 0.15 * recency_boost)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + weighted_rrf
            chunk_map[chunk_id] = chunk

        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda c_id: rrf_scores[c_id],
            reverse=True,
        )[:limit]

        ranked_results = [(chunk_map[c_id], rrf_scores[c_id]) for c_id in sorted_chunk_ids]

        logger.debug(
            "Executed Hybrid KB search with recency weighting",
            query_text=query_text,
            vector_hits=len(vec_results),
            lexical_hits=len(lex_results),
            merged_count=len(ranked_results),
        )
        return ranked_results

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Batch upsert knowledge chunks with conflict handling and metadata persistence.

        Args:
            chunks: List of chunk data dicts.

        Returns:
            Number of chunks successfully processed.
        """
        if not chunks:
            return 0

        for chunk_data in chunks:
            content_text = chunk_data.get("content", "")
            stmt = insert(KbChunkModel).values(
                chunk_id=chunk_data["chunk_id"],
                source_id=chunk_data.get("source_id", "kb"),
                title=chunk_data.get("title", ""),
                content=content_text,
                embedding=chunk_data["embedding"],
                category=chunk_data.get("category", "general"),
                location=chunk_data.get("location"),
                keywords=chunk_data.get("keywords", []),
                source=chunk_data.get("source", "knowledge_base_v1"),
                source_url=chunk_data.get("source_url"),
                source_type=chunk_data.get("source_type", "official"),
                data_version=chunk_data.get("data_version", "kb_v1.0"),
                city_alias=chunk_data.get("city_alias", []),
                scope_and_limitations=chunk_data.get("scope_and_limitations"),
                is_active=chunk_data.get("is_active", True),
                last_updated=chunk_data.get("last_updated"),
                content_tsvector=func.to_tsvector("simple", content_text),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["chunk_id"],
                set_={
                    "title": stmt.excluded.title,
                    "content": stmt.excluded.content,
                    "embedding": stmt.excluded.embedding,
                    "category": stmt.excluded.category,
                    "location": stmt.excluded.location,
                    "keywords": stmt.excluded.keywords,
                    "source": stmt.excluded.source,
                    "source_url": stmt.excluded.source_url,
                    "source_type": stmt.excluded.source_type,
                    "data_version": stmt.excluded.data_version,
                    "city_alias": stmt.excluded.city_alias,
                    "scope_and_limitations": stmt.excluded.scope_and_limitations,
                    "is_active": stmt.excluded.is_active,
                    "last_updated": stmt.excluded.last_updated,
                    "content_tsvector": stmt.excluded.content_tsvector,
                },
            )
            await self._session.execute(stmt)

        await self._session.commit()
        logger.info("Upserted KB chunks into database with metadata", count=len(chunks))
        return len(chunks)
