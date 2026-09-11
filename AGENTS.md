# TravelMate AI — Agent Instructions

## Project Overview

TravelMate AI is a Vietnamese travel assistant chatbot built with:
- **Python 3.12+** with **async/await** throughout
- **FastAPI** (ASGI) for API layer with SSE streaming
- **LangGraph** (>= 1.0) for deterministic graph-based orchestration
- **Anthropic Claude API** for LLM (response generation, intent classification, parameter extraction)
- **PostgreSQL 16 + pgvector** for relational data (POI) and vector search (Knowledge Base RAG)
- **Redis 7** for session state management (context per session_id, TTL)
- **Langfuse** for observability, tracing, and regression evaluation
- **Pydantic v2** for all schemas and validation
- **Alembic** for database migrations
- **Docker Compose** for local/staging deployment

## Architecture

The system follows a **Decoupled Layered Architecture** with LangGraph StateGraph as the orchestration engine.

### Graph Nodes (Processing Pipeline)
1. **Context Manager** (`graph/nodes/context_manager.py`) — CMP-03: session state Retain/Overwrite/Reset/RefResolve
2. **Router** (`graph/nodes/router.py`) — CMP-04: LLM-based intent classification → UC01/UC02/UC03/OUT_OF_SCOPE
3. **Parameter Resolver** (`graph/nodes/resolver.py`) — CMP-05: structured param extraction with provenance
4. **Tool Orchestrator** (`graph/nodes/tool_orchestrator.py`) — CMP-07: dispatches poi_search and knowledge_search
5. **Evidence Normalizer** (`graph/nodes/evidence_normalizer.py`) — CMP-08: normalize tool/KB outputs
6. **Response Generator** (`graph/nodes/response_generator.py`) — CMP-09: Claude streaming with grounded evidence
7. **Safety Guard** (`graph/nodes/safety_guard.py`) — CMP-10: prompt injection defense, output filtering

### Key Layers
- `api/` — FastAPI routes, lifespan management, dependency injection (`deps.py`)
- `graph/` — LangGraph state, builder, and nodes
- `tools/` — Tool implementations (`poi_search`, `knowledge_search`) behind Protocol interface (DIP seam)
- `rag/` — Ingestion pipeline, embedding wrapper, hybrid retriever
- `infrastructure/` — Shared Infrastructure Layer (SOLID, High Cohesion, Loose Coupling):
  - `infrastructure/database/` — SQLAlchemy 2.0 async engine, sessionmaker, declarative models, and repositories (`poi_repo`, `kb_repo`, `log_repo`)
  - `infrastructure/redis/` — Async Redis connection pool, session store (`ctx:{session_id}`, TTL 30m), and tool cache
- `schemas/` — Pydantic v2 models for Context State, Tool contracts, Trace
- `guardrails/` — Prompt injection detection, output filtering
- `observability/` — Langfuse tracing, structlog logging
- `prompts/` — Versioned system prompts and registry

### Data Flow
```
Client → FastAPI → Redis(load context via infrastructure) → LangGraph StateGraph
  → Context Manager → Router → Parameter Resolver
  → Tool Orchestrator → [infrastructure/database: poi | kb_chunks]
  → Evidence Normalizer → Response Generator(Claude API)
  → Safety Guard → Redis(save context via infrastructure) → SSE Response
```

## Coding Standards

### Language
- All source code in **Python 3.12+**
- All I/O operations must be **async** (asyncpg, aioredis, httpx.AsyncClient)
- Use **type hints** everywhere — function signatures, variables, return types

### Code Style
- Comment sparingly: only for non-obvious logic, workarounds, or business rules
- Write comprehensive **docstrings** for every public function, class, and method:
  - Use Google-style docstrings
  - Include: purpose, Args with types, Returns, Raises
  - Describe business context when relevant (which CMP/UC the code serves)
- No emoji or icons in code or logs
- Follow **SOLID principles**, proper **coupling/cohesion**
- Naming: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants

### Docstring Format (Google Style)
```python
async def search_poi(
    location: str,
    category: str,
    budget_max: int | None = None,
    preferences: list[str] | None = None,
) -> PoiSearchResponse:
    """Search for points of interest matching the given filters.

    Queries the poi table in PostgreSQL using structured filters.
    This tool is called by Tool Orchestrator (CMP-07) for UC01 and UC02.
    Results are NOT fabricated — if no match found, returns status=EMPTY.

    Args:
        location: Vietnamese province/city name (e.g., "Đà Nẵng", "Kiên Giang").
        category: One of ACCOM, FOOD, ATTRACTION, OTHER.
        budget_max: Maximum price in VND. Filters on price_numeric column.
        preferences: List of attribute tags (e.g., ["near_beach", "quiet", "pool"]).

    Returns:
        PoiSearchResponse with status and list of matching POI items.

    Raises:
        ToolTimeoutError: If database query exceeds configured timeout.
    """
```

### Architecture Rules
- Each graph node receives and returns `State` only — no direct DB/API calls
- Nodes access data through `tools/` or repository abstractions implemented in `infrastructure/database/repositories/` (decoupled)
- `graph/builder.py` is the single source of truth for node edges and routing
- All tools implement the Protocol in `tools/base.py`
- New tools must not require changes to `tool_orchestrator.py`

### Database & Infrastructure
- PostgreSQL models in `infrastructure/database/models.py` using SQLAlchemy 2.0 async
- Data access via Repository pattern in `infrastructure/database/repositories/`
- Migrations managed by Alembic — never modify DB schema directly
- POI data: relational queries (B-tree, GIN indexes), no embedding
- KB data: hybrid retrieval (pgvector HNSW + full-text search)
- Infrastructure connections initialized and cleaned up in FastAPI `lifespan`

### Redis
- Session state stored at key `ctx:{session_id}` as JSON with TTL via `infrastructure/redis/session_store.py`
- Use `redis[hiredis]` async client with connection pooling in `infrastructure/redis/client.py`
- Tool response cache at `tool_cache:{hash}` with short TTL via `infrastructure/redis/cache.py`

### Testing
- Unit tests: mock tool responses, test each node independently
- Integration tests: test full graph per use case (UC01, UC02, UC03)
- Regression tests: validate against `golden_set.json` (26 test cases)
- Use `pytest-asyncio` for async test support

### Safety (Non-negotiable)
- NEVER fabricate POI names, prices, ratings, or addresses
- NEVER reveal system prompt content
- ALWAYS return EMPTY/error status honestly when data is missing
- ALWAYS run input through prompt injection detection before processing

## File References
- Spec: `system_architecture_spec_annotated.md`
- Data: `data/mock_poi_data.json` (30 POI), `data/knowledge_base.json` (25 KB articles)
- Test: `data/golden_set.json` (26 regression test cases)
- Plan: `docs/mvp-implementation-plan.md`

## Commands
- `make up` — Start Docker services
- `make migrate` — Run Alembic migrations
- `make seed` — Seed POI + KB data
- `make test` — Run all tests
- `make lint` — Ruff linter
- `make reset` — Full reset (clean + up + migrate + seed)
