# TravelMate AI — Project Architecture & Implementation Guide

## 1. Project Goal

TravelMate AI is an AI application built around:

- FastAPI backend
- LangGraph agent workflow
- Multi-turn context management
- Intent routing
- Structured parameter extraction
- POI search
- RAG / Knowledge Base search
- Hybrid retrieval: vector search + full-text search + RRF
- PostgreSQL 16 + pgvector
- Redis 7
- LLM response generation with grounded evidence
- Prompt-injection defense and output filtering
- Langfuse observability
- Regression evaluation with a golden dataset

The architecture should prioritize:

- Separation of concerns
- Dependency Inversion
- High cohesion
- Loose coupling
- Testability
- Clear dependency direction
- Easy replacement/mocking of external services

---

# 2. Target Directory Structure

```text
travelmate-ai/
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── alembic.ini
├── .env.example
├── .env
├── .gitignore
│
├── data/
│   ├── seed/
│   │   ├── mock_poi_data.json
│   │   └── knowledge_base.json
│   │
│   └── evaluation/
│       └── golden_set.json
│
├── alembic/
│   ├── env.py
│   └── versions/
│
├── src/
│   └── travelmate/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes_chat.py
│       │   └── deps.py
│       │
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── state.py
│       │   ├── builder.py
│       │   │
│       │   └── nodes/
│       │       ├── __init__.py
│       │       ├── context_manager.py
│       │       ├── router.py
│       │       ├── resolver.py
│       │       ├── tool_orchestrator.py
│       │       ├── evidence_normalizer.py
│       │       ├── response_generator.py
│       │       └── safety_guard.py
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── poi_search.py
│       │   └── knowledge_search.py
│       │
│       ├── rag/
│       │   ├── __init__.py
│       │   ├── ingestion.py
│       │   ├── embeddings.py
│       │   └── retriever.py
│       │
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── llm_client.py
│       │   ├── embedding_client.py
│       │   └── langfuse_client.py
│       │
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   │
│       │   ├── database/
│       │   │   ├── __init__.py
│       │   │   ├── session.py
│       │   │   ├── models.py
│       │   │   │
│       │   │   └── repositories/
│       │   │       ├── __init__.py
│       │   │       ├── base.py
│       │   │       ├── poi_repo.py
│       │   │       ├── kb_repo.py
│       │   │       └── log_repo.py
│       │   │
│       │   └── redis/
│       │       ├── __init__.py
│       │       ├── client.py
│       │       ├── session_store.py
│       │       └── cache.py
│       │
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── context.py
│       │   ├── tools.py
│       │   ├── evidence.py
│       │   └── trace.py
│       │
│       ├── guardrails/
│       │   ├── __init__.py
│       │   ├── prompt_injection.py
│       │   └── output_filter.py
│       │
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── tracer.py
│       │   └── logger.py
│       │
│       └── prompts/
│           ├── system_prompt_v1.md
│           └── registry.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── regression/
│
└── scripts/
    ├── seed_poi.py
    ├── seed_kb.py
    └── eval_langfuse.py
```

---

# 3. Architecture Overview

The high-level request flow should be:

```text
                    ┌─────────────────┐
                    │    FastAPI      │
                    │      API        │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    LangGraph    │
                    │   StateGraph    │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   Context Manager         Router            Resolver
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                    ┌─────────────────┐
                    │ Tool Orchestrator│
                    └────────┬────────┘
                             │
                  ┌──────────┴──────────┐
                  ▼                     ▼
             POI Search             RAG Search
                  │                     │
                  │               ┌─────┴─────┐
                  │               │ Vector +  │
                  │               │    FTS    │
                  │               │    RRF    │
                  │               └─────┬─────┘
                  │                     │
                  └──────────┬──────────┘
                             ▼
                    Evidence Normalizer
                             │
                             ▼
                    Response Generator
                             │
                             ▼
                       Safety Guard
                             │
                             ▼
                         Response
```

Infrastructure dependencies:

```text
                  ┌───────────────────────┐
                  │      Application       │
                  │ API / Graph / Tools    │
                  │ RAG / Services         │
                  └───────────┬───────────┘
                              │
                     Protocols / Interfaces
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
         PostgreSQL          Redis          External APIs
         + pgvector                         LLM / Embeddings
```

---

# 4. Dependency Direction

Maintain this dependency direction:

```text
API
 ↓
Graph
 ↓
Tools / RAG / Services
 ↓
Protocols / Interfaces
 ↓
Infrastructure adapters
 ↓
PostgreSQL / Redis / External APIs
```

Do NOT introduce reverse dependencies such as:

```text
Infrastructure → Graph
Infrastructure → API
Repository → LangGraph
Repository → FastAPI
```

Graph nodes should NOT directly:

- create database connections
- create Redis clients
- instantiate SQLAlchemy sessions
- contain database-specific SQL
- hard-code external API clients

Instead, use dependency injection and protocols/interfaces.

---

# 5. API Layer

## `api/routes_chat.py`

Responsibilities:

- Define `/chat`
- Define `/health`
- Define `/version`
- Handle HTTP request/response concerns
- Handle SSE streaming for `/chat`
- Do not contain business logic

The route should invoke the graph/application workflow through injected dependencies.

## `api/deps.py`

Responsibilities:

- Dependency Injection
- Provide `AsyncSession`
- Provide repository implementations
- Provide SessionStore
- Provide graph/application dependencies

---

# 6. LangGraph Layer

## `graph/state.py`

Define the central LangGraph state.

The state should contain only application-level state, for example:

```text
session_id
user_message
intent
context
resolved_parameters
parameter_provenance
tool_requests
tool_results
evidence
response
trace
safety_status
```

Use typed schemas where possible.

## `graph/builder.py`

Responsibilities:

- Construct the LangGraph `StateGraph`
- Register nodes
- Define normal edges
- Define conditional edges
- Configure checkpointer
- Compile the graph

Keep node implementations outside the builder.

---

# 7. Graph Nodes

Every graph node should preferably have the form:

```python
async def node(state: TravelState) -> dict:
    ...
    return {
        "some_state_field": value
    }
```

The node should be easy to unit test independently.

---

## `context_manager.py`

CMP-03.

Responsibilities:

- Retain context
- Overwrite context
- Reset context
- Resolve references such as:
  - "ở đó"
  - "chỗ này"
  - "quán đó"
  - "ngày mai"
  - etc.
- Load/update session context through an abstraction

The node should depend on a SessionStore abstraction rather than directly depending on Redis.

Conceptual dependency:

```text
Context Manager
      ↓
SessionStore Protocol
      ↓
Redis Session Store
```

---

## `router.py`

CMP-04.

Responsibilities:

- LLM-based intent classification
- Classify into:
  - UC01
  - UC02
  - UC03
  - OOS

Return structured intent rather than free-form text.

Example:

```json
{
  "intent": "UC01",
  "confidence": 0.94
}
```

---

## `resolver.py`

CMP-05.

Responsibilities:

- Extract structured parameters
- Resolve missing values from context
- Track parameter provenance

Example:

```json
{
  "destination": {
    "value": "Hanoi",
    "source": "user",
    "confidence": 0.98
  }
}
```

Possible provenance sources:

```text
user
context
inferred
tool
system
```

Do not silently mix inferred values with user-provided values.

---

## `tool_orchestrator.py`

CMP-07.

Responsibilities:

- Decide which tools are needed
- Dispatch tool calls
- Handle tool errors
- Keep tool invocation behind abstractions
- Collect tool outputs

It should not implement POI database queries itself.

---

## `evidence_normalizer.py`

CMP-08.

Responsibilities:

- Normalize POI results
- Normalize Knowledge Base results
- Convert heterogeneous tool results into common `Evidence` objects
- Remove malformed or unusable evidence
- Preserve source metadata

Use `schemas/evidence.py` for the common contract.

Example:

```python
class Evidence(BaseModel):
    source_type: Literal["poi", "knowledge_base"]
    source_id: str
    title: str
    content: str
    score: float | None = None
```

---

## `response_generator.py`

CMP-09.

Responsibilities:

- Generate final grounded response
- Use normalized evidence
- Use the configured LLM
- Support streaming
- Avoid unsupported claims
- Respect system prompt/version

Keep actual LLM client implementation behind `clients/llm_client.py`.

Conceptually:

```text
Graph Node
    ↓
Response Service / Generator
    ↓
LLMClient
    ↓
Claude / other LLM
```

---

## `safety_guard.py`

CMP-10.

Responsibilities:

- Coordinate input safety checks
- Coordinate output filtering
- Block or modify unsafe responses

The actual security implementations live in:

```text
guardrails/
├── prompt_injection.py
└── output_filter.py
```

Therefore:

```text
Safety Guard Node
      │
      ├── Prompt Injection Detector
      └── Output Filter
```

Avoid duplicating guardrail logic inside the graph node.

---

# 8. Tool Layer

## `tools/base.py`

Define Protocols/interfaces for tools.

Example conceptual interface:

```python
class Tool(Protocol):
    name: str

    async def execute(self, request: ToolRequest) -> ToolResponse:
        ...
```

Tools should be replaceable and mockable.

---

## `tools/poi_search.py`

Responsibilities:

- Search POIs
- Consume `PoiRepositoryProtocol`
- Convert repository data into tool response
- Do not contain raw database connection management

Concept:

```text
POI Tool
   ↓
PoiRepositoryProtocol
   ↓
PostgreSQL Repository
```

---

## `tools/knowledge_search.py`

Responsibilities:

- Search the knowledge base
- Consume retriever/repository abstraction
- Return structured tool response

Concept:

```text
Knowledge Search Tool
        ↓
Hybrid Retriever
        ↓
KB Repository
        ↓
PostgreSQL + pgvector
```

---

# 9. RAG Layer

## `rag/ingestion.py`

Responsibilities:

```text
knowledge_base.json
        ↓
load documents
        ↓
clean/normalize
        ↓
chunk
        ↓
embedding
        ↓
store in PostgreSQL
```

Keep ingestion separate from query-time retrieval.

---

## `rag/embeddings.py`

Responsibilities:

- Hugging Face/serverless embedding client
- Embedding requests
- API key rotation if required
- Error handling/retry policy

Prefer exposing an abstraction that can be mocked.

---

## `rag/retriever.py`

Implement hybrid retrieval:

```text
                 Query
                   │
          ┌────────┴────────┐
          ▼                 ▼
     Vector Search       FTS Search
          │                 │
          └────────┬────────┘
                   ▼
                  RRF
                   │
                   ▼
                Top-K
```

Use:

- pgvector vector similarity
- PostgreSQL full-text search
- Reciprocal Rank Fusion (RRF)

The retriever should not own database connection lifecycle.

---

# 10. Clients Layer

Create a separate `clients/` layer for external service adapters.

## `clients/llm_client.py`

Abstraction around LLM provider.

Responsibilities:

- Chat completion
- Streaming
- Model configuration
- Timeouts
- Retries
- Error normalization

The rest of the application should not need to know provider-specific SDK details.

---

## `clients/embedding_client.py`

Abstraction around embedding provider.

Used by:

- RAG ingestion
- RAG retrieval

---

## `clients/langfuse_client.py`

Optional wrapper around Langfuse SDK.

Responsibilities:

- Trace creation
- Span/generation logging
- Metadata
- Prompt/model information
- Error tracking

---

# 11. Infrastructure Layer

Infrastructure contains concrete adapters.

## Database

### `database/session.py`

Responsibilities:

- Async SQLAlchemy engine
- Async sessionmaker
- Connection lifecycle
- PostgreSQL/asyncpg configuration
- pgvector codec setup if required
- Startup/shutdown integration

Do not expose database-specific setup to graph nodes.

---

## `database/models.py`

SQLAlchemy 2.0 models.

Expected main models:

```text
poi
kb_chunks
conversation_log
```

Possible fields should support:

### POI

```text
id
name
category
description
address
latitude
longitude
rating
metadata
created_at
updated_at
```

### KB chunk

```text
id
document_id
chunk_index
content
metadata
embedding
search_vector
created_at
```

### Conversation log

```text
id
session_id
trace_id
user_message
intent
resolved_parameters
tool_calls
response
metadata
created_at
```

Exact fields can be adapted to the functional requirements.

---

# 12. Repository Layer

Repositories are concrete database adapters.

## `repositories/base.py`

Define repository protocols/interfaces.

Examples:

```text
PoiRepositoryProtocol
KbRepositoryProtocol
ConversationLogRepositoryProtocol
```

Application/tool layers depend on these protocols rather than concrete SQLAlchemy repository classes.

---

## `poi_repo.py`

Responsibilities:

- CRUD/query operations for POIs
- Filtering
- Sorting
- Pagination if required
- Appropriate PostgreSQL indexes

Potential indexes:

```text
B-tree
GIN
```

Use only indexes that match actual query patterns.

---

## `kb_repo.py`

Responsibilities:

- Store/retrieve KB chunks
- Vector similarity search
- Full-text search
- Hybrid retrieval support
- RRF-related query logic where appropriate

Expected PostgreSQL features:

```text
pgvector
HNSW
FTS
GIN
```

---

## `log_repo.py`

Responsibilities:

- Persist conversation traces
- Persist audit information
- Do not implement logging/observability formatting

---

# 13. Redis Layer

## `redis/client.py`

Responsibilities:

- Create async Redis client/pool
- Ping health check
- Lifecycle management
- Configuration

---

## `redis/session_store.py`

Responsibilities:

- Store multi-turn context
- Retrieve context
- Update context
- Reset context
- TTL management

This is the concrete implementation behind the SessionStore abstraction.

---

## `redis/cache.py`

Responsibilities:

- Tool result caching
- Idempotency where applicable
- TTL
- Rate limiter backend

Do not mix conversation context and generic caching logic into one class.

---

# 14. Schemas

Use Pydantic v2.

## `schemas/context.py`

Contains:

- Context State
- Parameter Provenance
- Resolved parameters
- Context update operations

---

## `schemas/tools.py`

Contains:

- ToolRequest
- ToolResponse
- Tool error structures
- Tool metadata

---

## `schemas/evidence.py`

Contains common evidence contract.

Example:

```python
class Evidence(BaseModel):
    source_type: Literal["poi", "knowledge_base"]
    source_id: str
    title: str
    content: str
    score: float | None = None
```

All tools should eventually produce evidence that can be normalized into this structure.

---

## `schemas/trace.py`

Contains execution trace schema.

Should be able to represent:

```text
trace_id
session_id
intent
parameters
nodes
tool calls
retrieval
latency
errors
model
prompt_version
```

---

# 15. Guardrails

## `guardrails/prompt_injection.py`

Implement:

- Regex checks
- Heuristics
- Suspicious instruction detection
- Prompt injection patterns

Do not rely only on regex if stronger validation is practical.

---

## `guardrails/output_filter.py`

Implement:

- Sensitive information leak prevention
- Unsupported/fake entity filtering
- Evidence consistency checks
- Output sanitization

Do not blindly remove legitimate content.

---

# 16. Observability

## `observability/tracer.py`

Langfuse wrapper.

Track:

```text
request
 ↓
graph
 ↓
router
 ↓
resolver
 ↓
tool
 ↓
retrieval
 ↓
LLM
 ↓
response
```

Useful metadata:

```text
trace_id
session_id
prompt_version
model
latency
token usage
intent
tool calls
retrieved evidence
```

---

## `observability/logger.py`

Use structured logging, preferably `structlog`.

Include correlation information such as:

```text
request_id
trace_id
session_id
```

Do not log secrets, API keys, or unnecessary sensitive user data.

---

# 17. Prompt Management

## `prompts/system_prompt_v1.md`

Version-controlled system prompt.

The prompt should define:

- Assistant role
- Grounding requirements
- Tool/evidence rules
- Safety rules
- Response behavior
- Unsupported-claim policy

---

## `prompts/registry.py`

Responsibilities:

- Prompt version lookup
- Active prompt selection
- Prompt metadata

Example:

```text
v1
v2
...
```

Every relevant LLM trace should record the prompt version.

---

# 18. Data Layout

Use:

```text
data/
├── seed/
│   ├── mock_poi_data.json
│   └── knowledge_base.json
│
└── evaluation/
    └── golden_set.json
```

Reason:

- `seed/` = initial application data
- `evaluation/` = evaluation/regression data

Do not mix production-like seed data with evaluation datasets.

---

# 19. Scripts

## `scripts/seed_poi.py`

Load:

```text
data/seed/mock_poi_data.json
```

into PostgreSQL `poi`.

---

## `scripts/seed_kb.py`

Load:

```text
data/seed/knowledge_base.json
```

through the ingestion pipeline.

Expected flow:

```text
JSON
 ↓
chunk
 ↓
embed
 ↓
store
```

---

## `scripts/eval_langfuse.py`

Run regression evaluation against:

```text
data/evaluation/golden_set.json
```

Evaluate relevant dimensions such as:

- Intent correctness
- Parameter extraction
- Retrieval quality
- Groundedness
- Response correctness
- Safety behavior

Integrate results with Langfuse where practical.

---

# 20. Testing Strategy

## Unit tests

Test individual components without real external services.

Examples:

```text
router
resolver
context manager
prompt injection detector
output filter
retriever logic
evidence normalizer
tool dispatching
repositories with mocks
```

---

## Integration tests

Test real component interactions.

Examples:

```text
FastAPI → Graph
Graph → Tool
Tool → Repository
Repository → PostgreSQL
SessionStore → Redis
RAG → PostgreSQL + pgvector
```

Docker Compose can provide PostgreSQL and Redis for integration tests.

---

## Regression tests

Use:

```text
golden_set.json
```

to ensure changes to:

- prompts
- models
- retrieval
- routing
- context management

do not unexpectedly degrade behavior.

---

# 21. Docker

`docker-compose.yml` should provide local infrastructure such as:

```text
PostgreSQL 16 + pgvector
Redis 7
```

The application container should run the FastAPI application.

Keep secrets in `.env`, not in Dockerfiles or committed configuration.

---

# 22. Environment Configuration

`.env.example` should document required values such as:

```text
APP_ENV=
DEBUG=

DATABASE_URL=
REDIS_URL=

LLM_API_KEY=
LLM_MODEL=

EMBEDDING_API_KEY=
EMBEDDING_MODEL=

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=

PROMPT_VERSION=
```

Actual `.env` must not be committed.

---

# 23. Important Architectural Rules

## Rule 1 — Graph nodes stay thin

Prefer:

```text
Graph Node
    ↓
Service / abstraction
    ↓
Infrastructure adapter
```

Avoid putting large business logic inside graph nodes.

---

## Rule 2 — No direct infrastructure access from nodes

Bad:

```python
redis_client = Redis(...)
```

inside a graph node.

Bad:

```python
session.execute(...)
```

inside a graph node.

Prefer dependency injection.

---

## Rule 3 — Depend on abstractions

Prefer:

```text
Tool → PoiRepositoryProtocol
```

instead of:

```text
Tool → PostgresPoiRepository
```

This enables:

- mocking
- unit testing
- replacing implementations
- cleaner architecture

---

## Rule 4 — External SDKs stay behind clients

Avoid importing provider-specific SDKs throughout the application.

Prefer:

```text
Response Generator
       ↓
LLMClient
       ↓
Provider SDK
```

and:

```text
Retriever
       ↓
EmbeddingClient
       ↓
Embedding Provider SDK
```

---

## Rule 5 — Schemas define contracts

Use Pydantic models for communication between major layers.

Especially:

```text
Context
ToolRequest
ToolResponse
Evidence
Trace
```

---

## Rule 6 — Do not over-engineer

The architecture should remain understandable.

Do NOT create extra layers merely to demonstrate Clean Architecture.

Every abstraction should have a practical reason:

- testability
- replaceability
- dependency inversion
- separation of responsibility

---

# 24. Recommended End-to-End Flow

A normal `/chat` request should approximately follow:

```text
POST /chat
   │
   ▼
FastAPI route
   │
   ▼
Create/load graph state
   │
   ▼
Context Manager
   │
   ├── load session context
   └── resolve conversational references
   │
   ▼
Safety Guard (input)
   │
   ▼
Router
   │
   ├── UC01
   ├── UC02
   ├── UC03
   └── OOS
   │
   ▼
Resolver
   │
   ├── extract parameters
   ├── merge with context
   └── attach provenance
   │
   ▼
Tool Orchestrator
   │
   ├───────────────┐
   ▼               ▼
POI Search      KB Search
   │               │
   │          Hybrid Retriever
   │               │
   │        ┌──────┴──────┐
   │        ▼             ▼
   │     Vector          FTS
   │        └──────┬──────┘
   │               ▼
   │              RRF
   │               │
   └───────┬───────┘
           ▼
Evidence Normalizer
           │
           ▼
Response Generator
           │
           ▼
Safety Guard (output)
           │
           ▼
Persist trace/log
           │
           ▼
SSE response
```

---

# 25. Definition of Done

The implementation should eventually satisfy:

- [ ] FastAPI application starts successfully
- [ ] PostgreSQL + pgvector works
- [ ] Redis works
- [ ] Alembic migrations work
- [ ] POI seed script works
- [ ] KB ingestion works
- [ ] Embeddings are generated
- [ ] Vector search works
- [ ] FTS works
- [ ] RRF hybrid retrieval works
- [ ] Multi-turn context works
- [ ] Context TTL works
- [ ] Intent router works
- [ ] Structured resolver works
- [ ] Parameter provenance works
- [ ] Tool abstraction works
- [ ] POI tool works
- [ ] Knowledge search tool works
- [ ] Evidence normalization works
- [ ] Grounded LLM response works
- [ ] SSE streaming works
- [ ] Prompt injection defense works
- [ ] Output filtering works
- [ ] Langfuse tracing works
- [ ] Structured logging works
- [ ] Unit tests work
- [ ] Integration tests work
- [ ] Regression evaluation works

---

# 26. Implementation Priority

Implement in this order:

```text
1. Configuration
2. Docker / PostgreSQL / Redis
3. SQLAlchemy models + Alembic
4. Repository protocols + implementations
5. Seed POI / KB
6. Embedding client + RAG ingestion
7. Hybrid retriever
8. Tool abstractions
9. POI / Knowledge tools
10. Pydantic schemas
11. LangGraph state
12. Context manager
13. Router
14. Resolver
15. Tool orchestrator
16. Evidence normalizer
17. LLM client
18. Response generator
19. Guardrails
20. FastAPI + SSE
21. Observability / Langfuse
22. Unit tests
23. Integration tests
24. Regression evaluation
```

Build incrementally and keep the application runnable after each major step.

---

# 27. Final Architecture Principle

The project should feel like an AI application, not just an LLM wrapper.

The core architecture is:

```text
                 USER
                   │
                   ▼
              ┌─────────┐
              │ FastAPI │
              └────┬────┘
                   │
                   ▼
              ┌─────────┐
              │LangGraph│
              └────┬────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
    Context      Router      Resolver
       │           │           │
       └───────────┼───────────┘
                   ▼
             Orchestrator
              /         \
             ▼           ▼
          POI Tool     RAG Tool
             \           /
              \         /
               ▼       ▼
              Evidence
                  │
                  ▼
              LLM Response
                  │
                  ▼
               Guardrail
                  │
                  ▼
                USER
```

Infrastructure is replaceable underneath:

```text
PostgreSQL + pgvector
Redis
LLM Provider
Embedding Provider
Langfuse
```

Keep the dependency direction clean, keep graph nodes thin, and use abstractions at infrastructure boundaries.
