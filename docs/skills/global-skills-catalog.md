# Global Agent Skills Catalog

Catalog of reusable, global agent skills created from official documentation (fetched via Context7) and installed into `~/.agents/skills/`. These skills establish senior engineering standards, architecture patterns, and conventions applicable across all modern Python AI agent and backend projects.

---

## Skills Summary

| Skill Name | Technology | Category | Target Location |
|---|---|---|---|
| [`langgraph-python`](file:///Users/plxg/.agents/skills/langgraph-python/SKILL.md) | LangGraph (>= 1.0) | Multi-Agent Orchestration & Stateful Workflows | `~/.agents/skills/langgraph-python/` |
| [`fastapi-async-development`](file:///Users/plxg/.agents/skills/fastapi-async-development/SKILL.md) | FastAPI (>= 0.115) + Python 3.12+ | Async Web APIs & Real-time Streaming | `~/.agents/skills/fastapi-async-development/` |
| [`pgvector-hybrid-search`](file:///Users/plxg/.agents/skills/pgvector-hybrid-search/SKILL.md) | PostgreSQL 16 + pgvector + SQLAlchemy 2.0 | Vector Storage & Hybrid Retrieval (RRF) | `~/.agents/skills/pgvector-hybrid-search/` |
| [`langfuse-observability`](file:///Users/plxg/.agents/skills/langfuse-observability/SKILL.md) | Langfuse Python SDK (>= 2.50) | Observability, Tracing, Scoring & Evals | `~/.agents/skills/langfuse-observability/` |
| [`redis-development`](file:///Users/plxg/.agents/skills/redis-development/SKILL.md) | Redis 7 + Redis Query Engine | Session Store, Cache & Real-time Data | `~/.agents/skills/redis-development/` *(pre-existing)* |

---

## 1. LangGraph Python (`langgraph-python`)

- **Skill Location:** [`~/.agents/skills/langgraph-python/SKILL.md`](file:///Users/plxg/.agents/skills/langgraph-python/SKILL.md)
- **Domain:** Stateful LLM agent architectures, deterministic multi-step workflows, human-in-the-loop approvals.
- **Core Topics:**
  - **State Schemas & Reducers:** TypedDict and Pydantic v2 schemas; `Annotated[list, operator.add]` for append vs overwrite channels; custom deduplication reducers.
  - **Pure Node Functions:** Returning delta updates only; immutability rules; preventing direct in-place mutation of state dicts.
  - **Routing:** Static edges (`add_edge`) vs conditional edges (`add_conditional_edges`); map-reduce fan-out with `Send` API.
  - **Persistence & Checkpointing:** Session persistence, time-travel, and thread resume via `MemorySaver`, `AsyncSqliteSaver`, Redis, or PostgreSQL checkpointers.
  - **Multi-Mode Streaming:** Async streaming via `app.astream()` with modes `updates`, `values`, `messages`, and `custom`.
  - **Resilience & Breakpoints:** `RetryPolicy` configuration for transient network/LLM errors; `interrupt()` and `Command(resume=...)` for human approvals.

---

## 2. FastAPI Async Development (`fastapi-async-development`)

- **Skill Location:** [`~/.agents/skills/fastapi-async-development/SKILL.md`](file:///Users/plxg/.agents/skills/fastapi-async-development/SKILL.md)
- **Domain:** Production-ready asynchronous REST and SSE services with Python 3.12+.
- **Core Topics:**
  - **Modern Lifespan:** Resource allocation (HTTP clients, database pools, Redis connections) and clean teardown via `@asynccontextmanager lifespan(app: FastAPI)` (replacing deprecated `@app.on_event`).
  - **Async Dependency Injection:** Yield dependencies with automatic commit/rollback for transaction safety; clean dependency injection via `Annotated[T, Depends()]`.
  - **Pydantic v2 & Settings:** Schema serialization (`from_attributes=True`), input boundary validation, and environment configuration with `pydantic-settings`.
  - **Real-Time Streaming:** Server-Sent Events (SSE) and `StreamingResponse` with cooperative yielding (`await anyio.sleep(0)`) and client cancellation handling.
  - **Structured Error Handling:** Centralized exception handlers translating custom domain exceptions into standard RFC 7807 responses.
  - **Middleware & Observability:** ASGI middleware for `X-Request-ID` correlation and integration with structured logging (`structlog`).

---

## 3. pgvector & Hybrid Search (`pgvector-hybrid-search`)

- **Skill Location:** [`~/.agents/skills/pgvector-hybrid-search/SKILL.md`](file:///Users/plxg/.agents/skills/pgvector-hybrid-search/SKILL.md)
- **Domain:** Knowledge base vector embeddings, approximate nearest neighbor (ANN) search, and hybrid retrieval.
- **Core Topics:**
  - **Vector Schema Modeling:** Declarative SQLAlchemy models with `pgvector.sqlalchemy.VECTOR(dim)`.
  - **HNSW Indexing:** High-recall approximate indexing using `postgresql_using='hnsw'`, `m=16`, `ef_construction=64`, and operator class `vector_cosine_ops`.
  - **Async Codec Registration:** Binding vector codecs on `asyncpg` connections using `register_vector`.
  - **Hybrid Search (Dense + Lexical):** Overcoming vector semantic blindness on exact codes, names, or numbers by combining vector cosine distance with PostgreSQL Full-Text Search (`tsvector`, `to_tsquery`, GIN).
  - **Reciprocal Rank Fusion (RRF):** Merging rank positions from semantic and keyword searches into a unified score using `RRF = 1 / (60 + rank)`.
  - **Batch Upserts & Ingestion:** Conflict-free bulk ingestion with `on_conflict_do_update`.

---

## 4. Langfuse Observability (`langfuse-observability`)

- **Skill Location:** [`~/.agents/skills/langfuse-observability/SKILL.md`](file:///Users/plxg/.agents/skills/langfuse-observability/SKILL.md)
- **Domain:** End-to-end tracing, evaluation, prompt management, and telemetry for LLM applications.
- **Core Topics:**
  - **Distributed Tracing:** Decorator-based instrumentation with `@observe()` for tracking latency, call trees, and nested spans.
  - **Spans vs Generations:** Distinguishing business logic / tool spans from LLM generation observations capturing model names, hyperparameters, token usage, and costs.
  - **Evaluation & Scoring:** Programmatic scoring of runs (relevance, hallucination detection, user ratings) via `langfuse_context.score()`.
  - **Prompt Management:** Versioned prompt templates fetched and compiled at runtime with SDK-level caching.
  - **Dataset Benchmarking:** Offline regression testing and golden dataset evaluations with `langfuse.get_dataset()`.
  - **Graceful Flushing:** Calling `langfuse.flush()` in application lifespans to guarantee zero telemetry loss on worker exit.

---

## How Agents Discover These Skills

1. **Global Registration:** All 4 skills are registered in [`/Users/plxg/.agents/.skill-lock.json`](file:///Users/plxg/.agents/.skill-lock.json) under the `local` provider.
2. **Multi-Agent Compatibility:** Any AI assistant (Antigravity, Cursor, Codex, Copilot, Cline, etc.) operating on this machine will automatically discover and load these skills whenever working with LangGraph, FastAPI, pgvector, or Langfuse.
3. **Decoupled Design:** All rules, type definitions, and code samples are completely independent of any single project's domain logic, allowing them to be applied across any Python AI backend project.
