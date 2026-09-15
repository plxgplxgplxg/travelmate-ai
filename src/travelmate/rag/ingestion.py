"""Knowledge Base ingestion pipeline.

Parses knowledge_base.json, batches text chunks, generates 768d embeddings using
the Hugging Face Serverless client, and upserts them into the PostgreSQL pgvector
table through KbRepository.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from src.travelmate.infrastructure.database.repositories.kb_repo import KbRepository
from src.travelmate.rag.embeddings import HuggingFaceEmbeddingClient

logger = structlog.get_logger(__name__)


async def ingest_knowledge_base(
    json_path: Path | str,
    kb_repo: KbRepository,
    embedding_client: HuggingFaceEmbeddingClient,
    batch_size: int = 5,
) -> int:
    """Read knowledge base JSON, generate embeddings in batches, and persist to database.

    Args:
        json_path: Path to knowledge_base.json file.
        kb_repo: Active KbRepository instance.
        embedding_client: Initialized HuggingFaceEmbeddingClient.
        batch_size: Number of chunks to embed per API request.

    Returns:
        Total number of successfully ingested knowledge chunks.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge base file not found at: {path}")

    with open(path, encoding="utf-8") as f:
        articles: list[dict[str, Any]] = json.load(f)

    logger.info("Loaded knowledge base articles for ingestion", count=len(articles))

    all_chunks: list[dict[str, Any]] = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        # Combine title, keywords and content to maximize semantic vector retrieval coverage
        texts_to_embed = [
            f"{item.get('title', '')}. "
            f"Từ khóa: {', '.join(item.get('keywords', [])) if isinstance(item.get('keywords'), list) else str(item.get('keywords', ''))}. "
            f"Nội dung: {item.get('content', '')}"
            for item in batch
        ]

        # Generate embeddings with E5 passage prefix
        vectors = await embedding_client.embed_documents(texts_to_embed)

        for item, vector in zip(batch, vectors, strict=True):
            last_updated_val = None
            if item.get("last_updated"):
                try:
                    last_updated_val = datetime.strptime(item["last_updated"], "%Y-%m-%d").date()
                except ValueError:
                    last_updated_val = None

            chunk_record = {
                "chunk_id": item["kb_id"],
                "source_id": item["source_id"],
                "title": item["title"],
                "content": item["content"],
                "embedding": vector,
                "category": item.get("category", "general"),
                "location": item.get("location"),
                "keywords": item.get("keywords", []),
                "source": item.get("source", "knowledge_base_v1"),
                "source_url": item.get("source_url"),
                "source_type": item.get("source_type", "official"),
                "data_version": item.get("data_version", "kb_v1.0"),
                "city_alias": item.get("city_alias", []),
                "scope_and_limitations": item.get("scope_and_limitations"),
                "is_active": True,
                "last_updated": last_updated_val,
            }
            all_chunks.append(chunk_record)

        logger.debug(
            "Embedded batch of KB chunks", batch_index=i // batch_size + 1, batch_size=len(batch)
        )

    count = await kb_repo.upsert_chunks(all_chunks)
    logger.info("Successfully ingested knowledge base into PostgreSQL pgvector", total_chunks=count)
    return count
