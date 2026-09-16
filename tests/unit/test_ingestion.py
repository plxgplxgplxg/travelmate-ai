"""Unit tests for knowledge base ingestion pipeline (RAG, CMP-06, CMP-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.travelmate.clients.base import (
    EmbeddingClientProtocol,
    EmbeddingRateLimitError,
)
from src.travelmate.infrastructure.database.models import KbChunkModel
from src.travelmate.rag.ingestion import (
    estimate_token_count,
    ingest_knowledge_base,
)


class MockFlakyEmbeddingClient(EmbeddingClientProtocol):
    """Embedding client that fails with rate limit once before succeeding."""

    def __init__(self, fail_times: int = 1) -> None:
        self.fail_times = fail_times
        self.attempts = 0

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise EmbeddingRateLimitError("Rate limit exceeded")
        return [[0.05] * 768 for _ in documents]

    async def embed_query(self, query: str) -> list[float]:
        return [0.05] * 768

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_token_estimation() -> None:
    """Test token estimation utility for multilingual text."""
    short_text = "Thời tiết Đà Nẵng mùa hè rất đẹp."
    tokens = estimate_token_count(short_text)
    assert tokens > 0
    assert tokens < 50

    long_text = " ".join(["du lịch"] * 400)
    assert estimate_token_count(long_text) > 400


@pytest.mark.asyncio
async def test_ingest_knowledge_base_all_new(
    tmp_path: Path, mock_kb_repo, mock_embedding_client
) -> None:
    """Test full ingestion when all records are new."""
    sample_data = [
        {
            "kb_id": "KB_TEST_001",
            "source_id": "SRC_01",
            "title": "Kinh nghiệm du lịch Phú Quốc",
            "content": "Phú Quốc có nhiều bãi biển đẹp và ẩm thực phong phú.",
            "keywords": ["Phú Quốc", "Bãi Sao"],
            "location": "Kiên Giang",
            "category": "GENERAL",
            "last_updated": "2026-09-12",
        },
        {
            "kb_id": "KB_TEST_002",
            "source_id": "SRC_02",
            "title": "Ẩm thực Hội An",
            "content": "Cao lầu và mì Quảng là hai món ăn đặc sản không thể bỏ qua.",
            "keywords": ["Hội An", "ẩm thực"],
            "location": "Quảng Nam",
            "category": "FOOD",
            "last_updated": "2026-09-12",
        },
    ]
    json_file = tmp_path / "test_kb.json"
    json_file.write_text(json.dumps(sample_data), encoding="utf-8")

    mock_kb_repo.chunks = []

    count = await ingest_knowledge_base(
        json_path=json_file,
        kb_repo=mock_kb_repo,
        embedding_client=mock_embedding_client,
        batch_size=1,
    )

    assert count == 2
    assert len(mock_kb_repo.chunks) == 2
    assert mock_kb_repo.chunks[0].chunk_id == "KB_TEST_001"
    assert mock_kb_repo.chunks[1].chunk_id == "KB_TEST_002"


@pytest.mark.asyncio
async def test_ingest_skip_unchanged_content_hash(tmp_path: Path, mock_kb_repo) -> None:
    """Test skipping embedding for unchanged articles based on content hash."""
    sample_data = [
        {
            "kb_id": "KB_DN_WX_001",
            "source_id": "DOC_DANANG_TRAVEL_2025",
            "title": "Thời tiết Đà Nẵng theo mùa",
            "content": "Thời điểm lý tưởng nhất để du lịch Đà Nẵng là từ tháng 4 đến tháng 8.",
            "keywords": ["thời tiết Đà Nẵng", "mùa khô"],
            "last_updated": "2026-09-15",
        }
    ]
    json_file = tmp_path / "test_kb.json"
    json_file.write_text(json.dumps(sample_data), encoding="utf-8")

    class TrackingEmbeddingClient(EmbeddingClientProtocol):
        def __init__(self) -> None:
            self.called = False

        async def embed_documents(self, documents: list[str]) -> list[list[float]]:
            self.called = True
            return [[0.01] * 768]

        async def embed_query(self, query: str) -> list[float]:
            return [0.01] * 768

        async def close(self) -> None:
            pass

    tracking_client = TrackingEmbeddingClient()

    # KB_DN_WX_001 already exists in mock_kb_repo with the exact same content
    count = await ingest_knowledge_base(
        json_path=json_file,
        kb_repo=mock_kb_repo,
        embedding_client=tracking_client,
    )

    assert count == 1
    # Verify embedding client was NOT called because content hash matched
    assert tracking_client.called is False


@pytest.mark.asyncio
async def test_ingest_deactivate_orphan_chunks(
    tmp_path: Path, mock_kb_repo, mock_embedding_client
) -> None:
    """Test deactivating orphan chunks when an article is deleted from JSON."""
    mock_kb_repo.chunks = [
        KbChunkModel(
            chunk_id="KB_OLD_EVENT_2024",
            source_id="SRC_OLD",
            title="Sự kiện cũ 2024",
            content="Sự kiện này đã kết thúc.",
            embedding=[0.0] * 768,
            category="EVENT",
            is_active=True,
        ),
        KbChunkModel(
            chunk_id="KB_ACTIVE_001",
            source_id="SRC_NEW",
            title="Sự kiện mới 2026",
            content="Sự kiện sắp diễn ra.",
            embedding=[0.0] * 768,
            category="EVENT",
            is_active=True,
        ),
    ]

    # JSON only contains KB_ACTIVE_001; KB_OLD_EVENT_2024 has been removed
    sample_data = [
        {
            "kb_id": "KB_ACTIVE_001",
            "source_id": "SRC_NEW",
            "title": "Sự kiện mới 2026",
            "content": "Sự kiện sắp diễn ra.",
            "keywords": ["sự kiện"],
            "category": "EVENT",
        }
    ]
    json_file = tmp_path / "test_kb.json"
    json_file.write_text(json.dumps(sample_data), encoding="utf-8")

    await ingest_knowledge_base(
        json_path=json_file,
        kb_repo=mock_kb_repo,
        embedding_client=mock_embedding_client,
    )

    # Check that orphan chunk was marked is_active=False
    old_chunk = next(c for c in mock_kb_repo.chunks if c.chunk_id == "KB_OLD_EVENT_2024")
    assert old_chunk.is_active is False

    active_chunk = next(c for c in mock_kb_repo.chunks if c.chunk_id == "KB_ACTIVE_001")
    assert active_chunk.is_active is True


@pytest.mark.asyncio
async def test_ingest_retry_on_rate_limit(tmp_path: Path, mock_kb_repo) -> None:
    """Test that ingestion retries on rate limit errors using tenacity."""
    sample_data = [
        {
            "kb_id": "KB_FLAKY_001",
            "source_id": "SRC_FLAKY",
            "title": "Địa điểm du lịch mới",
            "content": "Nội dung cần embed có retry.",
            "keywords": ["mới"],
            "category": "GENERAL",
        }
    ]
    json_file = tmp_path / "test_kb.json"
    json_file.write_text(json.dumps(sample_data), encoding="utf-8")

    mock_kb_repo.chunks = []
    flaky_client = MockFlakyEmbeddingClient(fail_times=1)

    count = await ingest_knowledge_base(
        json_path=json_file,
        kb_repo=mock_kb_repo,
        embedding_client=flaky_client,
    )

    assert count == 1
    assert flaky_client.attempts == 2
    assert len(mock_kb_repo.chunks) == 1
