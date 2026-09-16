"""Knowledge Base ingestion pipeline.

Parses knowledge_base.json, skips unchanged records via SHA-256 content hashing,
estimates token lengths, generates 768d embeddings using Hugging Face Serverless client
with exponential retry backoff, persists incrementally per batch to PostgreSQL pgvector,
and deactivates orphan chunks.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.travelmate.clients.base import (
    EmbeddingClientProtocol,
    EmbeddingRateLimitError,
    EmbeddingServiceError,
)
from src.travelmate.infrastructure.database.repositories.base import KbRepositoryProtocol
from src.travelmate.infrastructure.database.repositories.kb_repo import compute_content_hash

logger = structlog.get_logger(__name__)


def estimate_token_count(text: str) -> int:
    """Estimate token count for multilingual text (approx 1.3 tokens per whitespace-separated word).

    Args:
        text: Input string.

    Returns:
        Estimated token count.
    """
    words = text.split()
    return int(len(words) * 1.3)


def _parse_date(date_str: str | None) -> date | None:
    """Safely parse YYYY-MM-DD date string.

    Args:
        date_str: Date string or None.

    Returns:
        date object if valid, None otherwise.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_chunk_record(item: dict[str, Any], vector: list[float]) -> dict[str, Any]:
    """Construct chunk dictionary for database insertion.

    Args:
        item: Raw article dictionary from JSON.
        vector: 768d dense embedding float vector.

    Returns:
        Dictionary formatted for KbRepository.upsert_chunks.
    """
    return {
        "chunk_id": item["kb_id"],
        "source_id": item.get("source_id", "kb"),
        "title": item.get("title", ""),
        "content": item.get("content", ""),
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
        "last_updated": _parse_date(item.get("last_updated")),
    }


def _build_metadata_record(item: dict[str, Any]) -> dict[str, Any]:
    """Construct metadata update dictionary for existing chunks without re-embedding.

    Args:
        item: Raw article dictionary from JSON.

    Returns:
        Dictionary formatted for KbRepository.update_chunk_metadata.
    """
    return {
        "chunk_id": item["kb_id"],
        "category": item.get("category", "general"),
        "location": item.get("location"),
        "source": item.get("source", "knowledge_base_v1"),
        "source_url": item.get("source_url"),
        "source_type": item.get("source_type", "official"),
        "data_version": item.get("data_version", "kb_v1.0"),
        "city_alias": item.get("city_alias", []),
        "scope_and_limitations": item.get("scope_and_limitations"),
        "last_updated": _parse_date(item.get("last_updated")),
    }


@retry(
    retry=retry_if_exception_type(
        (
            EmbeddingRateLimitError,
            EmbeddingServiceError,
            httpx.RequestError,
        )
    ),
    wait=wait_exponential(multiplier=1.5, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def _embed_documents_with_retry(
    embedding_client: EmbeddingClientProtocol,
    texts: list[str],
) -> list[list[float]]:
    """Embed document texts with exponential backoff retry.

    Note: The embedding client internally applies the E5 'passage: ' prefix.

    Args:
        embedding_client: Client implementing EmbeddingClientProtocol.
        texts: List of document strings to embed.

    Returns:
        List of float embedding vectors.
    """
    return await embedding_client.embed_documents(texts)


async def ingest_knowledge_base(
    json_path: Path | str,
    kb_repo: KbRepositoryProtocol,
    embedding_client: EmbeddingClientProtocol,
    batch_size: int = 5,
) -> int:
    """Read knowledge base JSON, generate embeddings in batches, and persist incrementally.

    Features:
    1. Resilient & Resumable: Batches are upserted and committed immediately to DB.
    2. Tenacity Retry: Automatic backoff on rate limits (HTTP 429), cold starts (HTTP 503), or network blips.
    3. Content Hash Optimization: Skips re-embedding unchanged records by comparing SHA-256 fingerprints.
    4. Orphan Cleanup: Deactivates (is_active=False) chunks that are removed from source JSON.
    5. Token Length Warning: Alerts when chunk content exceeds 400 tokens (near 512 context limit).

    Args:
        json_path: Path to knowledge_base.json file.
        kb_repo: Repository implementing KbRepositoryProtocol.
        embedding_client: Client implementing EmbeddingClientProtocol.
        batch_size: Number of chunks to embed per API request.

    Returns:
        Total number of processed knowledge chunks.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge base file not found at: {path}")

    with open(path, encoding="utf-8") as f:
        articles: list[dict[str, Any]] = json.load(f)

    logger.info("Loaded knowledge base articles for ingestion", count=len(articles))
    if not articles:
        return 0

    # 1. Compare content hash with DB to skip unchanged records and minimize embedding API costs
    existing_fingerprints = await kb_repo.get_existing_chunk_fingerprints()
    articles_to_embed: list[dict[str, Any]] = []
    unchanged_articles: list[dict[str, Any]] = []

    for item in articles:
        cid = item.get("kb_id", "")
        title = item.get("title", "")
        kw = item.get("keywords", [])
        content = item.get("content", "")
        current_hash = compute_content_hash(title, kw, content)

        if cid in existing_fingerprints and existing_fingerprints[cid] == current_hash:
            unchanged_articles.append(item)
        else:
            articles_to_embed.append(item)

    logger.info(
        "Ingestion delta evaluated",
        total=len(articles),
        to_embed=len(articles_to_embed),
        skipped_unchanged=len(unchanged_articles),
    )

    # 2. Update non-vector metadata for unchanged records without calling embedding API
    if unchanged_articles:
        metadata_records = [_build_metadata_record(item) for item in unchanged_articles]
        await kb_repo.update_chunk_metadata(metadata_records)

    # 3. Incremental batch embedding and persistence (resumable)
    total_embedded = 0
    for i in range(0, len(articles_to_embed), batch_size):
        batch = articles_to_embed[i : i + batch_size]
        texts_to_embed: list[str] = []

        for item in batch:
            kw_list = item.get("keywords", [])
            kw_str = ", ".join(kw_list) if isinstance(kw_list, list) else str(kw_list)
            text = (
                f"{item.get('title', '')}. Từ khóa: {kw_str}. Nội dung: {item.get('content', '')}"
            )

            # Check token length to avoid silent truncation by 512-token multilingual-e5
            est_tokens = estimate_token_count(text)
            if est_tokens > 400:
                logger.warning(
                    "KB chunk text length may exceed safe threshold for 512-token E5 model",
                    chunk_id=item.get("kb_id"),
                    estimated_tokens=est_tokens,
                    recommended_max=400,
                    max_context=512,
                )
            texts_to_embed.append(text)

        # Generate embeddings with tenacity retry (client handles E5 passage prefix internally)
        vectors = await _embed_documents_with_retry(embedding_client, texts_to_embed)

        batch_chunks = [
            _build_chunk_record(item, vector) for item, vector in zip(batch, vectors, strict=True)
        ]

        # Commit batch to PostgreSQL immediately
        await kb_repo.upsert_chunks(batch_chunks)
        total_embedded += len(batch_chunks)

        logger.debug(
            "Embedded and committed batch of KB chunks",
            batch_index=i // batch_size + 1,
            batch_size=len(batch),
            total_embedded=total_embedded,
        )

    # 4. Deactivate orphan chunks no longer present in source JSON
    all_json_ids = [item["kb_id"] for item in articles if "kb_id" in item]
    deactivated_count = await kb_repo.deactivate_orphan_chunks(all_json_ids)

    logger.info(
        "Completed knowledge base ingestion",
        total_articles=len(articles),
        embedded_count=total_embedded,
        unchanged_count=len(unchanged_articles),
        deactivated_orphans=deactivated_count,
    )
    return len(articles)
