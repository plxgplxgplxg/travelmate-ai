"""Database seed script for Knowledge Base chunks with pgvector embeddings.

Reads data/seed/knowledge_base.json (25 articles), generates 768d vector embeddings via
Hugging Face Serverless Inference API, and inserts chunks into the kb_chunks table.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from src.travelmate.clients.embedding_client import HuggingFaceEmbeddingClient
from src.travelmate.config import settings
from src.travelmate.infrastructure.database.repositories.kb_repo import KbRepository
from src.travelmate.infrastructure.database.session import close_db, get_db_session, init_db
from src.travelmate.rag.ingestion import ingest_knowledge_base

logger = structlog.get_logger(__name__)


async def seed_kb(json_file: Path | str | None = None) -> int:
    """Seed Knowledge Base records with pgvector embeddings into PostgreSQL.

    Args:
        json_file: Optional explicit path to knowledge base JSON file.

    Returns:
        Number of seeded knowledge chunks.
    """
    candidate_paths = (
        [Path(json_file)]
        if json_file
        else [
            Path("data/seed/knowledge_base_v1_3.json"),
            Path("data/seed/knowledge_base.json"),
            Path("knowledge_base_v1_3.json"),
            Path("knowledge_base.json"),
        ]
    )

    resolved_path: Path | None = None
    for p in candidate_paths:
        if p.exists():
            resolved_path = p
            break

    if not resolved_path:
        raise FileNotFoundError(f"Knowledge base file not found among candidates: {candidate_paths}")

    await init_db()

    embedding_client = HuggingFaceEmbeddingClient(
        api_keys=settings.hf_api_keys,
        model_name=settings.embedding_model,
        cooldown_seconds=settings.hf_rotation_cooldown_seconds,
        timeout=settings.hf_request_timeout_seconds,
    )

    try:
        async with get_db_session() as session:
            kb_repo = KbRepository(session=session)
            count = await ingest_knowledge_base(
                json_path=resolved_path,
                kb_repo=kb_repo,
                embedding_client=embedding_client,
                batch_size=5,
            )
            logger.info("Successfully seeded knowledge base", count=count)
            return count
    finally:
        await embedding_client.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed_kb())
