# TravelMate AI — MVP Implementation Plan

---

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph Client["Client Layer"]
        WEB["Web Client<br/>WebSocket / SSE"]
    end

    subgraph API["API Layer (FastAPI)"]
        GW["FastAPI Gateway<br/>Auth, Rate Limit, Validation"]
        DEPS["Dependency Injection<br/>api/deps.py"]
        LIFE["Lifespan Manager<br/>main.py (startup/teardown)"]
        GW --- DEPS
        GW --- LIFE
    end

    subgraph Orchestration["AI Agent Layer (LangGraph StateGraph)"]
        CM["Context Manager<br/>CMP-03"]
        RT["Router<br/>CMP-04"]
        PR["Parameter Resolver<br/>CMP-05"]
        TO["Tool Orchestrator<br/>CMP-07"]
        EN["Evidence Normalizer<br/>CMP-08"]
        RG["Response Generator<br/>CMP-09"]
        SG["Safety Guard<br/>CMP-10"]
    end

    subgraph Infra["Shared Infrastructure Layer (src/travelmate/infrastructure/)"]
        subgraph Infra_PG["Database (PostgreSQL 16 + pgvector)"]
            PG_POOL["Async Engine & Session Pool<br/>asyncpg + pgvector codec (session.py)"]
            PG_MODELS["Declarative Models<br/>poi, kb_chunks, conversation_log (models.py)"]
            PG_REPOS["Repositories (DIP/ISP Abstractions)<br/>PoiRepo, KbRepo, LogRepo"]
            PG_POOL --- PG_MODELS
            PG_MODELS --- PG_REPOS
        end

        subgraph Infra_Redis["Cache & State Store (Redis 7)"]
            RD_POOL["Connection Pool<br/>redis.asyncio (client.py)"]
            RD_STORE["Session Store (CMP-03)<br/>ctx:{session_id}, TTL 30m (session_store.py)"]
            RD_CACHE["Tool Cache & Rate Limiting<br/>tool_cache:{hash}, rate:{ip} (cache.py)"]
            RD_POOL --- RD_STORE
            RD_POOL --- RD_CACHE
        end
    end

    subgraph External["External Services"]
        DEEPSEEK["DeepSeek API<br/>deepseek-chat (V3)"]
        LF["Langfuse<br/>Observability"]
    end

    WEB -->|WebSocket/SSE| GW
    LIFE -.->|manages pool lifecycle| PG_POOL
    LIFE -.->|manages pool lifecycle| RD_POOL
    DEPS -->|injects AsyncSession| PG_POOL
    DEPS -->|injects SessionStore| RD_STORE
    GW -->|check rate limit| RD_CACHE

    GW --> CM
    CM -->|load/save context| RD_STORE
    CM --> RT
    RT -->|UC01/UC02/UC03/OOS| PR
    PR --> TO
    TO -->|poi_search / kb_search| PG_REPOS
    TO -->|idempotency cache| RD_CACHE
    TO --> EN
    EN --> RG
    RG --> DEEPSEEK
    RG --> SG
    SG -->|save context state| RD_STORE
    SG -->|stream| WEB

    CM -.->|trace| LF
    TO -.->|trace| LF
    RG -.->|trace| LF
```

---

## 2. Request Processing Workflow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI (API Layer)
    participant RS as Redis Store (Infrastructure)
    participant CM as Context Manager
    participant RT as Router
    participant PR as Param Resolver
    participant TO as Tool Orchestrator
    participant Repo as Postgres Repos (Infrastructure)
    participant EN as Evidence Normalizer
    participant RG as Response Generator
    participant SG as Safety Guard
    participant LLM as DeepSeek API (deepseek-chat)
    participant LF as Langfuse

    C->>API: POST /chat (message, session_id)
    API->>LF: Start trace
    API->>RS: Load context ctx:{session_id}
    RS-->>API: Context state JSON
    API->>CM: Merge query + context state
    CM->>RT: Route intent via LLM classification
    RT->>LLM: Classify UC01/UC02/UC03/OOS

    alt UC01 or UC02
        RT->>PR: Extract parameters
        PR->>LLM: Structured extraction Pydantic
        PR-->>TO: Validated params

        alt poi_search
            TO->>Repo: PoiRepository.search_poi(filters)
            Repo-->>TO: POI results
        end

        alt knowledge_search
            TO->>Repo: KbRepository.hybrid_search(vector + FTS)
            Repo-->>TO: KB chunks (RRF ranked)
        end

        TO->>EN: Normalize evidence
        EN->>RG: Grounded evidence
        RG->>LLM: Generate response streaming
        LLM-->>RG: Token stream
    end

    alt OUT_OF_SCOPE
        RT->>RG: Polite refusal
    end

    RG->>SG: Output guardrail check
    SG->>RS: Update context state ctx:{session_id}
    SG-->>API: Final response
    API-->>C: SSE stream
    API->>LF: End trace
```

---

## 3. Context Management Flow (UC03)

```mermaid
stateDiagram-v2
    [*] --> NewSession: First message
    NewSession --> HasContext: Extract params

    HasContext --> Retain: User adds info
    HasContext --> Overwrite: User changes info
    HasContext --> Reset: User says from scratch
    HasContext --> IntentSwitch: User changes intent
    HasContext --> RefResolve: User refers to results

    Retain --> HasContext: Merge new + keep old
    Overwrite --> HasContext: Replace specific field
    Reset --> NewSession: Clear all context
    IntentSwitch --> HasContext: Change intent keep location
    RefResolve --> HasContext: Resolve the 2nd one
```

---

## 4. Project Folder Structure

```
travelmate-ai/
├── pyproject.toml
├── .env.example
├── .env
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── data/
│   ├── mock_poi_data.json
│   ├── knowledge_base.json
│   └── golden_set.json
├── src/
│   └── travelmate/
│       ├── __init__.py
│       ├── main.py                     # FastAPI app factory + lifespan (quản lý pool DB & Redis từ infrastructure)
│       ├── config.py                   # Pydantic Settings: model, API keys, DB/Redis URLs, prompt version
│       ├── api/                        # API Layer (FastAPI)
│       │   ├── __init__.py
│       │   ├── routes_chat.py          # /chat (SSE streaming), /health, /version
│       │   └── deps.py                 # Dependency Injection (injects AsyncSession, Repositories, SessionStore)
│       ├── graph/                      # AI Agent Layer (LangGraph StateGraph)
│       │   ├── __init__.py
│       │   ├── state.py                # LangGraph State schema (map với Context State)
│       │   ├── builder.py              # StateGraph builder, conditional edges, checkpointer
│       │   └── nodes/                  # Pure Graph Nodes (chỉ nhận và trả về State, decoupled)
│       │       ├── __init__.py
│       │       ├── context_manager.py  # CMP-03: Retain/Overwrite/Reset/RefResolve (dùng SessionStore)
│       │       ├── router.py           # CMP-04: LLM intent classification (UC01/UC02/UC03/OOS)
│       │       ├── resolver.py         # CMP-05: Structured param extraction + provenance
│       │       ├── tool_orchestrator.py# CMP-07: Tool dispatching qua abstractions
│       │       ├── evidence_normalizer.py # CMP-08: Chuẩn hoá dữ liệu POI / KB
│       │       ├── response_generator.py  # CMP-09: Claude streaming grounded evidence
│       │       └── safety_guard.py     # CMP-10: Input injection defense & output filtering
│       ├── tools/                      # Tool layer (Protocols & dispatchers)
│       │   ├── __init__.py
│       │   ├── base.py                 # Tool Protocol interfaces (DIP abstraction seam)
│       │   ├── poi_search.py           # POI Search Tool (tiêu thụ PoiRepositoryProtocol)
│       │   └── knowledge_search.py     # KB Search Tool (tiêu thụ KbRepositoryProtocol)
│       ├── rag/                        # RAG Pipeline & Ingestion
│       │   ├── __init__.py
│       │   ├── ingestion.py            # Chunking pipeline nạp knowledge_base.json vào infrastructure
│       │   ├── embeddings.py           # Hugging Face serverless embedding client + key rotation
│       │   └── retriever.py            # Hybrid retriever interfacing với KbRepository (vector + FTS + RRF)
│       ├── infrastructure/             # Shared Infrastructure Layer (SOLID, High Cohesion, Loose Coupling)
│       │   ├── __init__.py
│       │   ├── database/               # PostgreSQL 16 + pgvector infrastructure
│       │   │   ├── __init__.py
│       │   │   ├── session.py          # Async engine, sessionmaker, lifespan lifecycle & asyncpg pgvector codec
│       │   │   ├── models.py           # SQLAlchemy 2.0 Declarative models (poi, kb_chunks, conversation_log)
│       │   │   └── repositories/       # Concrete Repository Adapters (SRP, DIP, ISP)
│       │   │       ├── __init__.py
│       │   │       ├── base.py         # Generic/Base repository protocol
│       │   │       ├── poi_repo.py     # Relational POI repository (B-tree & GIN filters)
│       │   │       ├── kb_repo.py      # Knowledge Base chunk repository (HNSW vector + FTS + RRF)
│       │   │       └── log_repo.py     # Conversation trace & audit log repository
│       │   └── redis/                  # Redis 7 infrastructure
│       │       ├── __init__.py
│       │       ├── client.py           # Async Redis connection pool, ping/health check & lifespan lifecycle
│       │       ├── session_store.py    # Multi-turn Context State store (CMP-03) with TTL
│       │       └── cache.py            # Tool result caching (idempotency, TTL) & rate limiter backend
│       ├── schemas/                    # Pydantic v2 schemas
│       │   ├── __init__.py
│       │   ├── context.py              # Context State, Parameter Provenance
│       │   ├── tools.py                # Tool request/response contracts
│       │   └── trace.py                # Execution Trace Schema (CMP-11)
│       ├── guardrails/                 # Security & Guardrails
│       │   ├── __init__.py
│       │   ├── prompt_injection.py     # Regex + heuristic prompt injection defense
│       │   └── output_filter.py        # Leak prevention & fake entity filtering
│       ├── observability/              # Observability & Tracing
│       │   ├── __init__.py
│       │   ├── tracer.py               # Langfuse tracing SDK wrapper
│       │   └── logger.py               # Structured logging (structlog) + correlation ID
│       └── prompts/                    # Versioned Prompt Management
│           ├── system_prompt_v1.md     # System instruction policy (CMP-01)
│           └── registry.py             # Prompt version registry (CMP-12)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── regression/
└── scripts/
    ├── seed_poi.py                     # Seed mock_poi_data.json -> bảng poi (PostgreSQL)
    ├── seed_kb.py                      # Seed knowledge_base.json -> bảng kb_chunks (pgvector)
    └── eval_langfuse.py                # Chạy regression evaluation dataset trên Langfuse
```

---

## 5. Shared Infrastructure & Database Architecture

Tầng **Infrastructure** (`src/travelmate/infrastructure/`) được thiết kế tách biệt đóng vai trò là nền tảng kỹ thuật dùng chung giữa **API Layer** (FastAPI Gateway, Lifespan, Dependency Injection, Rate Limiting) và **AI Agent Layer** (LangGraph StateGraph, Tool Orchestrator, Context Manager CMP-03, RAG Hybrid Search).

### 5.1. Infrastructure Architecture & Design Principles

```mermaid
graph LR
    subgraph Consumers["Consumers"]
        API["FastAPI Routes & Lifespan<br/>(api/routes_chat.py, main.py)"]
        AGENT["LangGraph Nodes & Tools<br/>(context_manager, poi_search, retriever)"]
    end

    subgraph Seams["Seams & Abstractions (Protocols)"]
        IPoiRepo["PoiRepositoryProtocol"]
        IKbRepo["KbRepositoryProtocol"]
        ISessionStore["SessionStoreProtocol"]
        ICache["CacheManagerProtocol"]
    end

    subgraph Infra["Shared Infrastructure Adapters"]
        subgraph DB_Module["infrastructure.database"]
            DBSession["session.py<br/>AsyncEngine, SessionMaker"]
            Models["models.py<br/>SQLAlchemy Declarative"]
            PoiRepo["repositories/poi_repo.py"]
            KbRepo["repositories/kb_repo.py"]
            LogRepo["repositories/log_repo.py"]
        end

        subgraph Redis_Module["infrastructure.redis"]
            RedisClient["client.py<br/>ConnectionPool, Ping"]
            RedisStore["session_store.py<br/>ContextState Serializer"]
            RedisCache["cache.py<br/>Key Hashing, TTL Cache"]
        end
    end

    API -->|DI via deps.py| DBSession
    API -->|DI via deps.py| RedisStore
    API -->|rate check| RedisCache

    AGENT -.->|depends on| IPoiRepo
    AGENT -.->|depends on| IKbRepo
    AGENT -.->|depends on| ISessionStore
    AGENT -.->|depends on| ICache

    PoiRepo -.->|implements| IPoiRepo
    KbRepo -.->|implements| IKbRepo
    RedisStore -.->|implements| ISessionStore
    RedisCache -.->|implements| ICache

    DBSession --> Models
    Models --> PoiRepo
    Models --> KbRepo
    Models --> LogRepo
    RedisClient --> RedisStore
    RedisClient --> RedisCache
```

#### 5.1.1. Tuân thủ Nguyên lý SOLID
1. **Single Responsibility Principle (SRP):**
   - `infrastructure/database/session.py`: Quản lý duy nhất vòng đời kết nối PostgreSQL (AsyncEngine, sessionmaker, codec pgvector).
   - `infrastructure/database/models.py`: Định nghĩa schema thực thể cơ sở dữ liệu.
   - `infrastructure/database/repositories/poi_repo.py`: Độc quyền xử lý nghiệp vụ truy vấn địa điểm POI dạng quan hệ.
   - `infrastructure/database/repositories/kb_repo.py`: Độc quyền xử lý Hybrid Search (Dense vector + FTS + RRF scoring).
   - `infrastructure/redis/client.py`: Quản lý connection pool và health check kết nối Redis.
   - `infrastructure/redis/session_store.py`: Quản lý serialization, deserialization và TTL cho Context State (CMP-03).
   - `infrastructure/redis/cache.py`: Quản lý cache kết quả tìm kiếm của Tool để giảm latency và chống gọi trùng lặp.
2. **Open/Closed Principle (OCP):**
   - Các repository và session store cài đặt dựa trên các protocol trừu tượng (`Protocol` trong Python). Khi cần nâng cấp sang Redis Cluster hoặc cơ sở dữ liệu vector chuyên biệt (như Qdrant), chỉ cần tạo adapter mới trong `infrastructure/` mà không cần sửa đổi mã nguồn của Agent Node hay API Routes.
3. **Liskov Substitution Principle (LSP):**
   - Các mock/in-memory repository (`MockPoiRepository`, `InMemorySessionStore`) thỏa mãn 100% chữ ký của Protocol, cho phép thay thế trực tiếp trong unit tests mà không làm gãy luồng thực thi của Router hay Tool Orchestrator.
4. **Interface Segregation Principle (ISP):**
   - API endpoints và các Tool chỉ phụ thuộc vào những method họ thực sự sử dụng. Ví dụ: `poi_search` chỉ biết đến `PoiRepositoryProtocol.search_poi()`, không truy cập hay can thiệp vào raw database session hay transaction commit/rollback.
5. **Dependency Inversion Principle (DIP):**
   - High-level modules (LangGraph nodes, FastAPI routes) không phụ thuộc trực tiếp vào low-level modules (SQLAlchemy session, asyncpg driver, redis-py). Chúng nhận dependency thông qua `api/deps.py` hoặc dependency injection container.

#### 5.1.2. Coupling & Cohesion
- **High Cohesion (Độ gắn kết cao):** Mọi logic liên quan đến I/O, driver, mapping schema, pooling, serialization và tối ưu hóa truy vấn dữ liệu được gom cụm chặt chẽ trong `src/travelmate/infrastructure/`.
- **Loose Coupling (Độ phụ thuộc lỏng):** API Layer và AI Agent Layer không giao tiếp trực tiếp qua các cấu trúc cơ sở dữ liệu nội bộ. Vòng đời kết nối được quản lý tập trung qua `lifespan` trong `main.py`.

---

### 5.2. PostgreSQL Tables (`infrastructure/database/models.py`)

```mermaid
erDiagram
    poi {
        text poi_id PK
        text name
        text address
        text location
        text category
        numeric rating
        bigint price_numeric
        text price_info
        jsonb attributes
        text source
        timestamp created_at
    }

    kb_chunks {
        text chunk_id PK
        text source_id
        text title
        text content
        vector(768) embedding
        text category
        text location
        jsonb keywords
        text source
        date last_updated
        timestamp created_at
    }

    conversation_log {
        uuid id PK
        text session_id
        text role
        text content
        jsonb context_snapshot
        text intent
        text bot_version
        timestamp created_at
    }

    poi ||--o{ conversation_log : "referenced in"
    kb_chunks ||--o{ conversation_log : "referenced in"
```

### 5.3. Data Ingestion Map

| Source File | Target Table | Engine | Embedding | Script |
|---|---|---|---|---|
| `mock_poi_data.json` (30 records) | `poi` | PostgreSQL | No | `scripts/seed_poi.py` |
| `knowledge_base.json` (25 articles) | `kb_chunks` | PostgreSQL + pgvector | Yes (`intfloat/multilingual-e5-base`, 768d) | `scripts/seed_kb.py` |
| `golden_set.json` (26 test cases) | Langfuse Dataset + `tests/regression/` | Langfuse API | No | `scripts/eval_langfuse.py` |

### 5.4. Redis Key & State Storage Design (`infrastructure/redis/`)

| Key Pattern | Type | TTL | Purpose | Quản lý bởi |
|---|---|---|---|---|
| `ctx:{session_id}` | JSON string | 30 min | Context state (CMP-03) | `infrastructure/redis/session_store.py` |
| `tool_cache:{hash}` | JSON string | 5 min | Tool response cache (Idempotency) | `infrastructure/redis/cache.py` |
| `rate:{client_ip}` | Counter | 1 min | Rate limiting middleware | `infrastructure/redis/cache.py` / `api` |

### 5.5. Indexes & Search Performance

**PostgreSQL:**
- `idx_poi_location_category` — B-tree on `(location, category)`
- `idx_poi_price` — B-tree on `price_numeric`
- `idx_poi_attributes` — GIN on `attributes`
- `idx_kb_embedding` — HNSW on `embedding` (pgvector, `vector_cosine_ops`)
- `idx_kb_content_fts` — GIN on `to_tsvector('simple', content)`
- `idx_conversation_session` — B-tree on `session_id`

### 5.6. Hugging Face Serverless Embedding Service (`rag/embeddings.py`)

#### 5.6.1. Model Selection Rationale
- **Selected Model:** `intfloat/multilingual-e5-base`
- **Dimensions:** 768
- **Why this model?**
  1. **Top Tier Benchmark for Vietnamese:** Dòng model E5 (Multilingual E5) xếp hạng cao nhất trong các bảng xếp hạng MTEB đa ngôn ngữ cho tác vụ Retrieval tiếng Việt. Vượt trội hoàn toàn so với `all-MiniLM-L6-v2` (vốn chủ yếu tối ưu tiếng Anh).
  2. **100% Miễn phí & Sẵn sàng trên Hugging Face Serverless Inference API:** Là featured model với hàng triệu lượt tải, luôn được Hugging Face duy trì warm container trên serverless API (`https://api-inference.huggingface.co/pipeline/feature-extraction/intfloat/multilingual-e5-base`).
  3. **E5 Prefix Convention:** Bắt buộc sử dụng prefix:
     - `passage: <nội dung KB>` khi embed chunk để lưu vào PostgreSQL pgvector.
     - `query: <câu hỏi tìm kiếm>` khi embed query của người dùng để tìm kiếm vector cosine similarity.
  4. **Dual-Key Rotation Architecture:** Miễn phí của Hugging Face giới hạn rate limit theo IP và Token. Bằng cách luân phiên xoay vòng giữa 2 access token (`HF_API_KEY_1`, `HF_API_KEY_2`) khi gặp mã lỗi `HTTP 429 Too Many Requests`, hệ thống tự động duy trì tính sẵn sàng cao mà không bị gián đoạn.

#### 5.6.2. Implementation Code (`src/travelmate/rag/embeddings.py`)

```python
"""Hugging Face Serverless Inference API embedding client with key rotation.

Provides async text embedding using Hugging Face's free Serverless Inference
API, featuring automatic dual-key rotation on HTTP 429 (rate limit) errors,
E5 prefix formatting, and retry handling.
Serves CMP-07 (Tool Orchestrator) and RAG hybrid retrieval for UC01/UC02.
"""

from __future__ import annotations

import asyncio
import time
from typing import Sequence
import httpx
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingRateLimitError(Exception):
    """Raised when all configured Hugging Face API keys exceed rate limits."""


class EmbeddingServiceError(Exception):
    """Raised when the Hugging Face inference API returns an unrecoverable error."""


class HFKeyRotator:
    """Thread-safe and async-safe API key rotator with cooldown tracking.

    Manages multiple Hugging Face API tokens, tracking rate-limiting state
    and automatically rotating to the next valid key when HTTP 429 occurs.
    """

    def __init__(self, keys: Sequence[str], default_cooldown_seconds: float = 60.0) -> None:
        """Initialize the key rotator.

        Args:
            keys: List of Hugging Face API tokens (e.g., [HF_API_KEY_1, HF_API_KEY_2]).
            default_cooldown_seconds: Default penalty cooldown time in seconds on 429.

        Raises:
            ValueError: If the keys list is empty.
        """
        if not keys:
            raise ValueError("At least one Hugging Face API key must be provided.")
        self._keys = [k.strip() for k in keys if k.strip()]
        if not self._keys:
            raise ValueError("No valid non-empty Hugging Face API keys found.")
        self._cooldown_seconds = default_cooldown_seconds
        self._cooldown_until: dict[str, float] = {k: 0.0 for k in self._keys}
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    async def get_active_key(self) -> str:
        """Get the currently active API key that is not in cooldown.

        Returns:
            The active Hugging Face API token string.

        Raises:
            EmbeddingRateLimitError: If all keys are currently in cooldown.
        """
        async with self._lock:
            now = time.monotonic()
            key = self._keys[self._current_index]
            if self._cooldown_until[key] <= now:
                return key

            for idx, candidate in enumerate(self._keys):
                if self._cooldown_until[candidate] <= now:
                    self._current_index = idx
                    logger.info("Switched to active HF API key", key_index=idx)
                    return candidate

            min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
            raise EmbeddingRateLimitError(
                f"All {len(self._keys)} HF API keys are rate-limited. "
                f"Earliest cooldown reset in {min_remaining:.1f}s."
            )

    async def mark_rate_limited(self, key: str, custom_cooldown: float | None = None) -> str:
        """Mark a key as rate-limited (HTTP 429) and advance to the next key.

        Args:
            key: The key that hit HTTP 429.
            custom_cooldown: Optional cooldown in seconds (e.g., from Retry-After header).

        Returns:
            The next key to try.

        Raises:
            EmbeddingRateLimitError: If all keys have been exhausted.
        """
        async with self._lock:
            cooldown = custom_cooldown or self._cooldown_seconds
            self._cooldown_until[key] = time.monotonic() + cooldown
            logger.warning(
                "HF API key rate-limited, cooling down",
                masked_key=f"{key[:6]}...{key[-4:]}",
                cooldown_seconds=cooldown,
            )

            self._current_index = (self._current_index + 1) % len(self._keys)
            next_key = self._keys[self._current_index]

            now = time.monotonic()
            if self._cooldown_until[next_key] > now:
                for idx, candidate in enumerate(self._keys):
                    if self._cooldown_until[candidate] <= now:
                        self._current_index = idx
                        return candidate

                min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
                raise EmbeddingRateLimitError(
                    f"All {len(self._keys)} HF API keys exhausted after rotation. "
                    f"Cooldown reset in {min_remaining:.1f}s."
                )

            return next_key


class HuggingFaceEmbeddingClient:
    """Async client for Hugging Face Serverless Inference API with key rotation.

    Embeds text chunks and search queries using intfloat/multilingual-e5-base
    (768 dimensions), strictly prefixing queries with 'query: ' and passages
    with 'passage: ' as required by the E5 model family.
    """

    def __init__(
        self,
        api_keys: Sequence[str],
        model_name: str = "intfloat/multilingual-e5-base",
        timeout: float = 30.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        """Initialize the embedding client.

        Args:
            api_keys: List of 2 or more Hugging Face access tokens.
            model_name: Model identifier on Hugging Face Hub (default: intfloat/multilingual-e5-base).
            timeout: HTTP request timeout in seconds.
            cooldown_seconds: Rate limit cooldown period in seconds.
        """
        self.model_name = model_name
        self.endpoint_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}"
        self.rotator = HFKeyRotator(api_keys, default_cooldown_seconds=cooldown_seconds)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Send embedding request with automatic key rotation on 429 and retry on 503.

        Args:
            texts: List of prepared strings (with prefix).

        Returns:
            List of 768-dimensional float embedding vectors.

        Raises:
            EmbeddingRateLimitError: If all keys are rate-limited.
            EmbeddingServiceError: If API call fails after retries.
        """
        max_attempts = len(self.rotator._keys) * 2
        for attempt in range(max_attempts):
            key = await self.rotator.get_active_key()
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": texts,
                "options": {"wait_for_model": True},
            }

            try:
                response = await self.client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data and isinstance(data[0], list):
                        return data
                    elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
                        return [data]
                    raise EmbeddingServiceError(f"Unexpected response format from HF API: {type(data)}")

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    cooldown = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
                    await self.rotator.mark_rate_limited(key, custom_cooldown=cooldown)
                    continue

                if response.status_code == 503:
                    logger.info("HF model is loading (cold start), waiting 5 seconds...")
                    await asyncio.sleep(5.0)
                    continue

                raise EmbeddingServiceError(
                    f"HF Inference API returned HTTP {response.status_code}: {response.text}"
                )

            except httpx.RequestError as exc:
                logger.error("HTTP request error to HF API", error=str(exc))
                if attempt == max_attempts - 1:
                    raise EmbeddingServiceError(f"HF API request failed: {exc}") from exc
                await asyncio.sleep(1.0)

        raise EmbeddingRateLimitError("Exceeded maximum retry attempts across all API keys.")

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of knowledge base document chunks for vector indexing.

        Automatically prepends the 'passage: ' prefix required by multilingual-e5 models.

        Args:
            documents: List of text content from knowledge base articles.

        Returns:
            List of 768-dimensional embedding vectors.
        """
        if not documents:
            return []
        prefixed = [f"passage: {doc}" for doc in documents]
        return await self._embed_with_retry(prefixed)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single search query for hybrid vector retrieval.

        Automatically prepends the 'query: ' prefix required by multilingual-e5 models.

        Args:
            query: User search query or synthesized query string.

        Returns:
            768-dimensional embedding vector for cosine similarity search.
        """
        prefixed = [f"query: {query}"]
        vectors = await self._embed_with_retry(prefixed)
        return vectors[0]
```

---

## 6. Docker Services

```mermaid
graph LR
    subgraph compose["docker-compose"]
        APP["app<br/>FastAPI + LangGraph<br/>:8000"]
        PG["postgres<br/>PostgreSQL 16 + pgvector<br/>:5432"]
        RD["redis<br/>Redis 7<br/>:6379"]
        LF["langfuse<br/>Langfuse Server<br/>:3000"]
        LF_PG["langfuse-db<br/>PostgreSQL 16<br/>:5433"]
    end

    APP --> PG
    APP --> RD
    APP --> LF
    LF --> LF_PG
```

### Services Summary

| Service | Image | Port | Volume | Depends On |
|---|---|---|---|---|
| `app` | Build from `Dockerfile` | 8000 | `./src:/app/src` | postgres, redis |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | `pg_data` | - |
| `redis` | `redis:7-alpine` | 6379 | `redis_data` | - |
| `langfuse` | `langfuse/langfuse:latest` | 3000 | - | langfuse-db |
| `langfuse-db` | `postgres:16-alpine` | 5433 | `langfuse_data` | - |

---

## 7. MVP Implementation Phases

### Phase 1: Infrastructure & Skeleton (2-3 days)

- [ ] Init project: `pyproject.toml`, dependencies, `.env.example`
- [ ] Docker Compose: postgres(pgvector), redis, langfuse, app
- [ ] Dockerfile (multi-stage)
- [ ] Infrastructure setup: AsyncEngine pool (`infrastructure/database/session.py`), Redis connection pool (`infrastructure/redis/client.py`)
- [ ] FastAPI app factory + lifespan (`main.py` managing infrastructure pool lifecycle & health checks)
- [ ] Alembic setup + initial migration (poi, kb_chunks, conversation_log)
- [ ] Pydantic Settings (`config.py`)
- [ ] Makefile

### Phase 2: Shared Infrastructure & Data Layer (1-2 days)

- [ ] Declarative SQLAlchemy models (`infrastructure/database/models.py`)
- [ ] Repository pattern with DIP protocols (`infrastructure/database/repositories/poi_repo.py`, `kb_repo.py`, `log_repo.py`)
- [ ] Redis session store with TTL & caching (`infrastructure/redis/session_store.py`, `cache.py`)
- [ ] Dependency injection adapters (`api/deps.py`)
- [ ] Seed scripts: `seed_poi.py`, `seed_kb.py`
- [ ] RAG ingestion pipeline (`rag/ingestion.py`, `rag/embeddings.py`)

### Phase 3: Core Graph Nodes (3-4 days)

- [ ] LangGraph State schema (`graph/state.py`)
- [ ] Context Manager node (Retain/Overwrite/Reset/RefResolve)
- [ ] Router node (LLM classification -> UC01/UC02/UC03/OOS)
- [ ] Parameter Resolver node (structured extraction)
- [ ] Tool Orchestrator node (poi_search, knowledge_search)
- [ ] Evidence Normalizer node
- [ ] Response Generator node (DeepSeek-V3 streaming)
- [ ] Safety Guard node (input/output)
- [ ] Graph builder with conditional edges (`graph/builder.py`)

### Phase 4: API & Integration (1-2 days)

- [ ] `/chat` endpoint (SSE streaming)
- [ ] `/health`, `/version` endpoints
- [ ] System prompt v1 (`prompts/system_prompt_v1.md`)
- [ ] Langfuse tracing integration
- [ ] structlog setup

### Phase 5: Testing & Validation (1-2 days)

- [ ] Unit tests per node (mock tool responses)
- [ ] Integration tests per UC (UC01, UC02, UC03)
- [ ] Regression test runner with golden_set.json
- [ ] Langfuse evaluation dataset upload

**Total estimated: 8-13 days**

---

## 8. Tech Stack Summary

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.12+ |
| API | FastAPI + Uvicorn | latest |
| Orchestration | LangGraph | >= 1.0 |
| LLM | DeepSeek API (`deepseek-chat` / DeepSeek-V3) | latest (OpenAI-compatible) |
| Embedding | Hugging Face Serverless Inference API (`intfloat/multilingual-e5-base`) | 768 dims (Free Tier + Dual-Key Rotation) |
| Database | PostgreSQL + pgvector | 16 + 0.7 |
| Session/Cache | Redis | 7 |
| HTTP Client | httpx + tenacity | latest |
| Validation | Pydantic v2 | latest |
| Observability | Langfuse | latest |
| Logging | structlog | latest |
| Migration | Alembic | latest |
| Container | Docker + Docker Compose | latest |

---

## 9. Makefile

```makefile
.PHONY: help up down build logs migrate seed test lint format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === Docker ===

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build Docker images
	docker compose build

rebuild: ## Force rebuild and start
	docker compose up -d --build --force-recreate

logs: ## Tail logs all services
	docker compose logs -f

logs-app: ## Tail app logs only
	docker compose logs -f app

logs-db: ## Tail postgres logs only
	docker compose logs -f postgres

restart-app: ## Restart app service only
	docker compose restart app

# === Database ===

migrate: ## Run Alembic migrations
	docker compose exec app alembic upgrade head

migrate-new: ## Create new migration. Usage: make migrate-new MSG="add poi table"
	docker compose exec app alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	docker compose exec app alembic downgrade -1

migrate-history: ## Show migration history
	docker compose exec app alembic history

# === Seed Data ===

seed: seed-poi seed-kb ## Seed all data

seed-poi: ## Seed POI data 30 records
	docker compose exec app python -m scripts.seed_poi

seed-kb: ## Seed Knowledge Base 25 articles with embedding
	docker compose exec app python -m scripts.seed_kb

# === App ===

run-local: ## Run app locally without Docker
	uvicorn src.travelmate.main:app --reload --host 0.0.0.0 --port 8000

shell: ## Open shell in app container
	docker compose exec app bash

db-shell: ## Open psql in postgres container
	docker compose exec postgres psql -U travelmate -d travelmate_db

redis-cli: ## Open redis-cli
	docker compose exec redis redis-cli

# === Testing ===

test: ## Run all tests
	docker compose exec app pytest tests/ -v

test-unit: ## Run unit tests
	docker compose exec app pytest tests/unit/ -v

test-integration: ## Run integration tests
	docker compose exec app pytest tests/integration/ -v

test-regression: ## Run regression tests golden set
	docker compose exec app pytest tests/regression/ -v

test-cov: ## Run tests with coverage
	docker compose exec app pytest tests/ --cov=src/travelmate --cov-report=term-missing

# === Code Quality ===

lint: ## Run linter ruff
	docker compose exec app ruff check src/ tests/

format: ## Format code ruff
	docker compose exec app ruff format src/ tests/

typecheck: ## Run type checker mypy
	docker compose exec app mypy src/travelmate

# === Evaluation ===

eval: ## Run Langfuse evaluation with golden set
	docker compose exec app python -m scripts.eval_langfuse

# === Cleanup ===

clean: ## Remove volumes and orphans
	docker compose down -v --remove-orphans

reset: clean up migrate seed ## Full reset: clean + up + migrate + seed
```

---

## 10. Key Dependencies (pyproject.toml)

```toml
[project]
name = "travelmate-ai"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "langgraph>=1.0",
    "langchain-openai>=0.2",
    "langchain-core>=0.3",
    "openai>=1.50",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "pgvector>=0.3",
    "alembic>=1.14",
    "redis[hiredis]>=5.0",
    "httpx>=0.28",
    "tenacity>=9.0",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.0",
    "langfuse>=2.50",
    "sse-starlette>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.8",
    "mypy>=1.13",
    "httpx",
]
```

---

## 11. Environment Variables & Configuration

### 11.1. `.env.example` (Template)

```env
# ==============================================================================
# TravelMate AI — Environment Variables Template (.env.example)
# Copy to .env and fill in the required credentials before running.
# ==============================================================================

# === LLM Engine (DeepSeek-V3 / deepseek-chat — Primary LLM) ===
# Platform: https://platform.deepseek.com
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-xxxx-your-deepseek-key-here
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2

# Optional Fallback LLM (Anthropic Claude if needed):
# ANTHROPIC_API_KEY=sk-ant-api03-xxxx-your-key-here
# ANTHROPIC_MODEL=claude-sonnet-4-20250514

# === Embedding (Hugging Face Serverless Inference API — Free Tier) ===
# intfloat/multilingual-e5-base: 768 dims, top-tier Vietnamese retrieval on MTEB.
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIMENSION=768

# Hugging Face Dual-Key Rotation:
# Create 2 free tokens at https://huggingface.co/settings/tokens (Read permissions)
HF_API_KEY_1=hf_your_first_huggingface_read_token_here
HF_API_KEY_2=hf_your_second_huggingface_read_token_here
HF_ROTATION_COOLDOWN_SECONDS=60
HF_REQUEST_TIMEOUT_SECONDS=30.0

# === PostgreSQL App DB (pgvector enabled) ===
DATABASE_URL=postgresql+asyncpg://travelmate:travelmate_pass@postgres:5432/travelmate_db
POSTGRES_USER=travelmate
POSTGRES_PASSWORD=travelmate_pass
POSTGRES_DB=travelmate_db

# === Redis Context Store & Cache ===
REDIS_URL=redis://redis:6379/0
REDIS_SESSION_TTL=1800

# === Langfuse Observability ===
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_HOST=http://langfuse:3000

# === Langfuse Database (Self-hosted) ===
LANGFUSE_DATABASE_URL=postgresql://langfuse:langfuse_pass@langfuse-db:5433/langfuse_db

# === Application Configuration ===
APP_ENV=development
APP_DEBUG=true
BOT_VERSION=V1.0
SYSTEM_PROMPT_VERSION=v1
LOG_LEVEL=DEBUG

# === API Gateway & Security ===
RATE_LIMIT_PER_MINUTE=60
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:5173
API_SECRET_KEY=generate-with-openssl-rand-hex-32
```

### 11.2. Mẫu `.env` Thực Tế (Local Development Sample)

```env
# ==============================================================================
# TravelMate AI — Local Development Environment Sample (.env)
# ==============================================================================

# === LLM Engine (DeepSeek-V3 Official) ===
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-sampledevtestdeepseekkey1234567890abcdef
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2

# === Embedding (Hugging Face Serverless Inference API — Free Tier) ===
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIMENSION=768
HF_API_KEY_1=hf_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345678
HF_API_KEY_2=hf_zYxWvUtSrQpOnMlKjIhGfEdCbA87654321
HF_ROTATION_COOLDOWN_SECONDS=60
HF_REQUEST_TIMEOUT_SECONDS=30.0

# === PostgreSQL App DB ===
DATABASE_URL=postgresql+asyncpg://travelmate:travelmate_pass@localhost:5432/travelmate_db
POSTGRES_USER=travelmate
POSTGRES_PASSWORD=travelmate_pass
POSTGRES_DB=travelmate_db

# === Redis ===
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_TTL=1800

# === Langfuse Observability ===
LANGFUSE_SECRET_KEY=sk-lf-dev-secret-key-placeholder
LANGFUSE_PUBLIC_KEY=pk-lf-dev-public-key-placeholder
LANGFUSE_HOST=http://localhost:3000

# === Langfuse DB ===
LANGFUSE_DATABASE_URL=postgresql://langfuse:langfuse_pass@localhost:5433/langfuse_db

# === App Config ===
APP_ENV=development
APP_DEBUG=true
BOT_VERSION=V1.0
SYSTEM_PROMPT_VERSION=v1
LOG_LEVEL=DEBUG

# === API Gateway ===
RATE_LIMIT_PER_MINUTE=60
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:5173

# === Security ===
API_SECRET_KEY=e4d909c290d0fb1ca068ffaddf22cbd0ffd607f2ef8c1b3f790209c169222cf7
```

### 11.3. Checklist: API Keys & Services

| Item | Nguồn Cung Cấp | Yêu Cầu | Ghi Chú |
|---|---|---|---|
| `OPENAI_API_KEY` (DeepSeek) | [platform.deepseek.com](https://platform.deepseek.com) | Bắt buộc | Model `deepseek-chat` (DeepSeek-V3), tặng credit free ban đầu |
| `HF_API_KEY_1`, `HF_API_KEY_2` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | Bắt buộc | Tạo 2 User Access Tokens quyền `Read`, hoàn toàn miễn phí |
| Embedding Model | Serverless Inference API `intfloat/multilingual-e5-base` (768 dims) | Miễn phí | Tự động xoay giữa 2 key khi gặp HTTP 429 rate limit |
| `LANGFUSE_SECRET_KEY` + `PUBLIC_KEY` | Self-host qua Docker hoặc [cloud.langfuse.com](https://cloud.langfuse.com) | Bắt buộc | Dashboard tự host tại `http://localhost:3000` |
| `API_SECRET_KEY` | Tạo ngẫu nhiên bằng `openssl rand -hex 32` | Bắt buộc | Dùng để ký token hoặc xác thực nội bộ API |
| PostgreSQL 16 + pgvector | Docker Compose tự khởi tạo | Đã cấu hình | Chạy trên port 5432, lưu trữ POI và KB 768d vectors |
| Redis 7 | Docker Compose tự khởi tạo | Đã cấu hình | Chạy trên port 6379, lưu context session và tool cache |

> **Lưu ý về LLM & Hugging Face Inference API:**
> - **LLM DeepSeek-V3 (`deepseek-chat`):** Cung cấp API chuẩn OpenAI (`https://api.deepseek.com/v1`). Khả năng tuân thủ schema JSON và tiếng Việt bản địa vượt trội, chi phí cực thấp (~$0.14-$0.28 / 1M tokens).
> - **Embedding `intfloat/multilingual-e5-base` (768 dims):** Model embedding đa ngôn ngữ mạnh nhất hiện tại trên Hugging Face có hỗ trợ serverless inference miễn phí.
> - **Format văn bản:** Thư viện E5 yêu cầu prefix `"passage: "` khi index KB chunks và `"query: "` khi tìm kiếm.
> - **Cơ chế xoay key:** Khi key 1 chạm rate limit (HTTP 429), `HFKeyRotator` tự động chuyển sang key 2 và đưa key 1 vào thời gian nghỉ (cooldown 60s), giúp hệ thống hoạt động liên tục mà không phát sinh chi phí.
