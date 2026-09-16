"""Unit tests for Phase 3 tools and HybridRetriever (CMP-06, CMP-07)."""

from __future__ import annotations

from typing import Any

import pytest

from src.travelmate.infrastructure.database.models import KbChunkModel, PoiModel
from src.travelmate.rag.retriever import HybridRetriever
from src.travelmate.tools.base import ToolProtocol
from src.travelmate.tools.knowledge_search import KnowledgeSearchTool
from src.travelmate.tools.poi_search import PoiSearchTool


@pytest.mark.asyncio
async def test_poi_search_tool_success(mock_poi_repo) -> None:
    """Test PoiSearchTool successful execution with matching records."""
    tool = PoiSearchTool(poi_repo=mock_poi_repo)
    params = {
        "location": "Đà Nẵng",
        "category": "ACCOM",
        "budget_max": 1000000,
        "preferences": ["near_beach"],
    }

    response = await tool.execute(params)

    assert response["status"] == "OK"
    assert len(response["items"]) == 1
    assert response["items"][0]["name"] == "Khách sạn Canvas Đà Nẵng"
    assert response["items"][0]["category"] == "ACCOM"
    assert response["items"][0]["price_numeric"] == 750000


@pytest.mark.asyncio
async def test_poi_search_tool_empty(mock_poi_repo) -> None:
    """Test PoiSearchTool returns EMPTY status when no records match (BR-No-Fabrication)."""
    tool = PoiSearchTool(poi_repo=mock_poi_repo)
    params = {
        "location": "Hà Giang",
        "category": "ACCOM",
        "budget_max": 100000,
    }

    response = await tool.execute(params)

    assert response["status"] == "EMPTY"
    assert response["items"] == []
    assert response["error"] is None


@pytest.mark.asyncio
async def test_poi_search_tool_bad_request(mock_poi_repo) -> None:
    """Test PoiSearchTool validation failure on missing required parameters."""
    tool = PoiSearchTool(poi_repo=mock_poi_repo)
    # Missing required 'location' parameter
    params = {"category": "ACCOM"}

    response = await tool.execute(params)

    assert response["status"] == "BAD_REQUEST"
    assert response["error"] is not None
    assert response["error"]["code"] == "ERR-PARAM-01"


@pytest.mark.asyncio
async def test_poi_search_tool_provider_error() -> None:
    """Test PoiSearchTool handles database execution errors gracefully."""

    class BrokenPoiRepo:
        async def search_poi(self, *args: Any, **kwargs: Any) -> list[PoiModel]:
            raise ConnectionError("Database connection lost")

        async def get_by_id(self, poi_id: str) -> PoiModel | None:
            return None

    tool = PoiSearchTool(poi_repo=BrokenPoiRepo())  # type: ignore[arg-type]
    params = {"location": "Đà Nẵng", "category": "ACCOM"}

    response = await tool.execute(params)

    assert response["status"] == "PROVIDER_ERROR"
    assert response["error"] is not None
    assert response["error"]["code"] == "ERR-TOOL-01"
    assert "Database connection lost" in response["error"]["message"]


@pytest.mark.asyncio
async def test_knowledge_search_tool_success(mock_kb_repo, mock_embedding_client) -> None:
    """Test KnowledgeSearchTool execution with matching knowledge chunks."""
    retriever = HybridRetriever(kb_repo=mock_kb_repo, embedding_client=mock_embedding_client)
    tool = KnowledgeSearchTool(retriever=retriever)
    params = {
        "query": "Thời tiết Đà Nẵng",
        "location": "Đà Nẵng",
    }

    response = await tool.execute(params)

    assert response["status"] == "OK"
    assert len(response["chunks"]) > 0
    assert response["chunks"][0]["title"] == "Thời tiết Đà Nẵng theo mùa"
    assert response["chunks"][0]["chunk_id"] == "KB_DN_WX_001"


@pytest.mark.asyncio
async def test_knowledge_search_tool_empty(mock_embedding_client) -> None:
    """Test KnowledgeSearchTool returns EMPTY status when no chunks match."""

    class EmptyKbRepo:
        async def hybrid_search(
            self, *args: Any, **kwargs: Any
        ) -> list[tuple[KbChunkModel, float]]:
            return []

        async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
            return 0

    retriever = HybridRetriever(kb_repo=EmptyKbRepo(), embedding_client=mock_embedding_client)  # type: ignore[arg-type]
    tool = KnowledgeSearchTool(retriever=retriever)
    params = {"query": "Thông tin không tồn tại"}

    response = await tool.execute(params)

    assert response["status"] == "EMPTY"
    assert response["chunks"] == []
    assert response["error"] is None


@pytest.mark.asyncio
async def test_knowledge_search_tool_bad_request(mock_kb_repo, mock_embedding_client) -> None:
    """Test KnowledgeSearchTool validation failure when query is missing."""
    retriever = HybridRetriever(kb_repo=mock_kb_repo, embedding_client=mock_embedding_client)
    tool = KnowledgeSearchTool(retriever=retriever)
    params = {}  # Missing required 'query'

    response = await tool.execute(params)

    assert response["status"] == "ERROR"
    assert response["error"] is not None
    assert response["error"]["code"] == "ERR-PARAM-01"


@pytest.mark.asyncio
async def test_knowledge_search_tool_execution_error(mock_embedding_client) -> None:
    """Test KnowledgeSearchTool handles retriever errors gracefully."""

    class FailingKbRepo:
        async def hybrid_search(
            self, *args: Any, **kwargs: Any
        ) -> list[tuple[KbChunkModel, float]]:
            raise RuntimeError("pgvector index corrupted")

        async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
            return 0

    retriever = HybridRetriever(kb_repo=FailingKbRepo(), embedding_client=mock_embedding_client)  # type: ignore[arg-type]
    tool = KnowledgeSearchTool(retriever=retriever)
    params = {"query": "Thời tiết"}

    response = await tool.execute(params)

    assert response["status"] == "ERROR"
    assert response["error"] is not None
    assert response["error"]["code"] == "ERR-RAG-01"
    assert "pgvector index corrupted" in response["error"]["message"]


@pytest.mark.asyncio
async def test_knowledge_search_tool_init_variations(mock_kb_repo, mock_embedding_client) -> None:
    """Test KnowledgeSearchTool initialization through RetrieverProtocol contract."""
    # 1. Direct HybridRetriever injection
    retriever = HybridRetriever(kb_repo=mock_kb_repo, embedding_client=mock_embedding_client)
    tool1 = KnowledgeSearchTool(retriever)
    res1 = await tool1.execute({"query": "test"})
    assert res1["status"] == "OK"

    # 2. Keyword retriever injection
    tool2 = KnowledgeSearchTool(retriever=retriever)
    res2 = await tool2.execute({"query": "test"})
    assert res2["status"] == "OK"

    # 3. Custom RetrieverProtocol mock injection
    class CustomRetriever:
        async def retrieve(self, query: str, **kwargs: Any) -> list[Any]:
            return []

    tool3 = KnowledgeSearchTool(retriever=CustomRetriever())  # type: ignore[arg-type]
    res3 = await tool3.execute({"query": "test"})
    assert res3["status"] == "EMPTY"


@pytest.mark.asyncio
async def test_hybrid_retriever_retrieve(mock_kb_repo, mock_embedding_client) -> None:
    """Test HybridRetriever correctly generates embedding and retrieves chunks."""
    retriever = HybridRetriever(kb_repo=mock_kb_repo, embedding_client=mock_embedding_client)

    chunks = await retriever.retrieve(
        query="Du lịch Đà Nẵng",
        category="SEASON_WEATHER",
        location="Đà Nẵng",
        top_k=2,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == "KB_DN_WX_001"
    assert chunk.title == "Thời tiết Đà Nẵng theo mùa"
    assert chunk.score == 0.95


def test_tool_protocol_compliance(mock_poi_repo, mock_kb_repo, mock_embedding_client) -> None:
    """Test that all tool classes conform to ToolProtocol interface."""
    import inspect

    poi_tool = PoiSearchTool(poi_repo=mock_poi_repo)
    retriever = HybridRetriever(kb_repo=mock_kb_repo, embedding_client=mock_embedding_client)
    kb_tool = KnowledgeSearchTool(retriever=retriever)

    assert isinstance(poi_tool, ToolProtocol)
    assert isinstance(kb_tool, ToolProtocol)
    assert "idempotency_key" not in inspect.signature(poi_tool.execute).parameters
    assert "idempotency_key" not in inspect.signature(kb_tool.execute).parameters
