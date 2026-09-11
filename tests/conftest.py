"""Pytest fixtures and in-memory mock adapters for unit and integration testing.

Allows testing LangGraph nodes, tools, and clients in total isolation without requiring
live PostgreSQL, Redis, or external LLM APIs (LSP / DIP adherence).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
import pytest

from src.travelmate.clients.embedding_client import EmbeddingClientProtocol
from src.travelmate.clients.llm_client import LLMClientProtocol
from src.travelmate.infrastructure.database.models import KbChunkModel, PoiModel
from src.travelmate.infrastructure.database.repositories.base import (
    KbRepositoryProtocol,
    PoiRepositoryProtocol,
)
from src.travelmate.infrastructure.redis.cache import CacheManagerProtocol
from src.travelmate.infrastructure.redis.session_store import SessionStoreProtocol
from src.travelmate.schemas.context import ContextState, IntentEnum, LocationState


class MockLLMClient(LLMClientProtocol):
    """In-memory mock satisfying LLMClientProtocol."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.default_response = "Dưới đây là gợi ý du lịch phù hợp cho bạn."
        self.calls: list[list[dict[str, str]]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(messages)
        user_content = messages[-1]["content"] if messages else ""

        for key, resp in self.responses.items():
            if key in user_content:
                return resp

        if json_mode:
            # Return appropriate default JSON
            if "phân loại ý định" in str(messages):
                return '{"intent": "UC01_FIND_PLACE", "confidence": 0.95, "reasoning": "Mock classification"}'
            if "bóc tách tham số" in str(messages):
                return '{"location": "Đà Nẵng", "category": "ACCOM", "budget_max": 2000000, "preferences": ["near_beach"]}'
            return "{}"

        return self.default_response

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        full_text = await self.complete(messages, temperature, max_tokens)
        for word in full_text.split(" "):
            yield word + " "


class MockEmbeddingClient(EmbeddingClientProtocol):
    """In-memory mock satisfying EmbeddingClientProtocol."""

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [[0.05] * self.dimension for _ in documents]

    async def embed_query(self, query: str) -> list[float]:
        return [0.05] * self.dimension

    async def close(self) -> None:
        pass


class MockPoiRepository(PoiRepositoryProtocol):
    """In-memory mock satisfying PoiRepositoryProtocol."""

    def __init__(self, sample_pois: list[PoiModel] | None = None) -> None:
        self.pois = sample_pois or [
            PoiModel(
                poi_id="POI_DN_ACC_001",
                name="Khách sạn Danang Golden Bay",
                address="15 Đường Bạch Đằng, Quận Hải Châu",
                location="Đà Nẵng",
                category="ACCOM",
                rating=4.6,
                price_info="2,500,000 VND/đêm",
                price_numeric=2500000,
                attributes=["near_beach", "pool", "luxury"],
                source="Muong Thanh Hospitality",
                source_url="https://booking.muongthanh.com/khach-san-danang",
                source_type="official",
            ),
            PoiModel(
                poi_id="POI_DN_ACC_002",
                name="Khách sạn Canvas Đà Nẵng",
                address="76 Hà Bổng, Quận Sơn Trà",
                location="Đà Nẵng",
                category="ACCOM",
                rating=4.3,
                price_info="750,000 VND/đêm",
                price_numeric=750000,
                attributes=["near_beach", "budget", "quiet"],
                source="Canvas Hotel Official",
                source_url="https://canvashotel.com.vn/",
                source_type="official",
            ),
            PoiModel(
                poi_id="POI_DN_FOD_001",
                name="Bánh Mì Phượng Hội An",
                address="2B Phan Châu Trinh, Hội An",
                location="Quảng Nam",
                category="FOOD",
                rating=4.7,
                price_info="35,000 VND/phần",
                price_numeric=35000,
                attributes=["traditional", "street_food"],
                source="Vietnam Tourism",
                source_url="https://vietnam.travel/things-to-do/hoi-an-food",
                source_type="official",
            ),
        ]

    async def search_poi(
        self,
        location: str,
        category: str,
        budget_min: int | None = None,
        budget_max: int | None = None,
        preferences: list[str] | None = None,
        limit: int = 5,
    ) -> list[PoiModel]:
        loc_lower = location.lower()
        results = [
            p
            for p in self.pois
            if (loc_lower in p.location.lower() or any(loc_lower in alias.lower() for alias in getattr(p, "city_alias", [])))
            and p.category.upper() == category.upper()
        ]
        if budget_max is not None:
            results = [p for p in results if p.price_numeric <= budget_max]
        if preferences:
            pref_set = set(preferences)
            results = [p for p in results if any(tag in pref_set for tag in p.attributes)]
        return results[:limit]

    async def get_by_id(self, poi_id: str) -> PoiModel | None:
        for p in self.pois:
            if p.poi_id == poi_id:
                return p
        return None


class MockKbRepository(KbRepositoryProtocol):
    """In-memory mock satisfying KbRepositoryProtocol."""

    def __init__(self, sample_chunks: list[KbChunkModel] | None = None) -> None:
        self.chunks = sample_chunks or [
            KbChunkModel(
                chunk_id="KB_DN_WX_001",
                source_id="DOC_DANANG_TRAVEL_2025",
                title="Thời tiết Đà Nẵng theo mùa",
                content="Thời điểm lý tưởng nhất để du lịch Đà Nẵng là từ tháng 4 đến tháng 8.",
                embedding=[0.01] * 768,
                category="SEASON_WEATHER",
                location="Đà Nẵng",
                keywords=["thời tiết Đà Nẵng", "mùa khô"],
                source="Climatestotravel",
                source_url="https://www.climatestotravel.com/climate/vietnam/da-nang",
                source_type="public_web",
                data_version="kb_v1.3",
                is_active=True,
            )
        ]

    async def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        category_filter: str | None = None,
        location_filter: str | None = None,
        limit: int = 3,
        rrf_k: int = 60,
    ) -> list[tuple[KbChunkModel, float]]:
        hits = [(chunk, 0.95) for chunk in self.chunks if getattr(chunk, "is_active", True)]
        return hits[:limit]

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        return len(chunks)


class InMemorySessionStore(SessionStoreProtocol):
    """In-memory dictionary store satisfying SessionStoreProtocol."""

    def __init__(self) -> None:
        self.storage: dict[str, dict[str, Any]] = {}

    async def get_context(self, session_id: str) -> dict[str, Any] | None:
        return self.storage.get(session_id)

    async def save_context(
        self,
        session_id: str,
        context_data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        self.storage[session_id] = context_data

    async def clear_context(self, session_id: str) -> None:
        self.storage.pop(session_id, None)


class InMemoryCacheManager(CacheManagerProtocol):
    """In-memory mock for tool caching and rate limiting."""

    def __init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {}
        self.rates: dict[str, int] = {}

    def make_cache_key(self, tool_name: str, params: dict[str, Any]) -> str:
        return f"{tool_name}:{str(sorted(params.items()))}"

    async def get_cached(self, key: str) -> dict[str, Any] | None:
        return self.cache.get(key)

    async def set_cached(self, key: str, value: dict[str, Any], ttl_seconds: int = 300) -> None:
        self.cache[key] = value

    async def is_rate_limited(self, identifier: str, limit: int = 60, window_seconds: int = 60) -> bool:
        count = self.rates.get(identifier, 0) + 1
        self.rates[identifier] = count
        return count > limit


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """Fixture providing a mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def mock_embedding_client() -> MockEmbeddingClient:
    """Fixture providing a mock embedding client."""
    return MockEmbeddingClient()


@pytest.fixture
def mock_poi_repo() -> MockPoiRepository:
    """Fixture providing an in-memory POI repository."""
    return MockPoiRepository()


@pytest.fixture
def mock_kb_repo() -> MockKbRepository:
    """Fixture providing an in-memory KB repository."""
    return MockKbRepository()


@pytest.fixture
def mock_session_store() -> InMemorySessionStore:
    """Fixture providing an in-memory session store."""
    return InMemorySessionStore()


@pytest.fixture
def mock_cache_mgr() -> InMemoryCacheManager:
    """Fixture providing an in-memory cache manager."""
    return InMemoryCacheManager()


@pytest.fixture
def sample_context() -> ContextState:
    """Fixture providing a baseline ContextState."""
    return ContextState(
        session_id="test_sess_001",
        current_intent=IntentEnum.UC01_FIND_PLACE,
        location=LocationState(value="Đà Nẵng", source="explicit"),
        preferences=["near_beach"],
    )
