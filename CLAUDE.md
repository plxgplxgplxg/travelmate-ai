# TravelMate AI — Claude Agent Instructions

## Project

TravelMate AI — Vietnamese travel assistant chatbot.
Stack: Python 3.12+, FastAPI, LangGraph (>=1.0), Anthropic Claude API, PostgreSQL 16 + pgvector, Redis 7, Langfuse, Pydantic v2, Alembic, Docker Compose.

## Architecture

Decoupled Layered Architecture with LangGraph StateGraph orchestration.

Graph nodes pipeline: Context Manager → Router → Parameter Resolver → Tool Orchestrator → Evidence Normalizer → Response Generator → Safety Guard.

Key directories:
- `src/travelmate/api/` — FastAPI routes, DI
- `src/travelmate/graph/` — LangGraph state, builder, nodes
- `src/travelmate/tools/` — Tool Protocol + implementations (poi_search, knowledge_search)
- `src/travelmate/rag/` — Ingestion, embedding, hybrid retriever
- `src/travelmate/infrastructure/` — Shared Infrastructure (PostgreSQL 16 + pgvector, Redis 7, repositories, session store, cache)
- `src/travelmate/schemas/` — Pydantic models (context, tools, trace)
- `src/travelmate/guardrails/` — Prompt injection, output filter
- `src/travelmate/observability/` — Langfuse tracer, structlog
- `src/travelmate/prompts/` — Versioned system prompts

## Coding Rules

1. Python 3.12+, all I/O async (asyncpg, aioredis, httpx.AsyncClient)
2. Type hints on all functions, variables, returns
3. Comments: minimal, only for non-obvious logic or business rules
4. Docstrings: comprehensive Google-style on every public function/class/method
   - Include: purpose, Args (with types), Returns, Raises
   - Reference which CMP/UC component the code serves
5. No emoji/icons in code or logs
6. SOLID principles, proper coupling/cohesion
7. snake_case functions/variables, PascalCase classes, UPPER_CASE constants
8. Each graph node only receives/returns State — access data via tools/ or infrastructure/database/repositories/
9. graph/builder.py is the single source of truth for routing edges
10. All tools implement Protocol from tools/base.py
11. Never fabricate data. Never reveal system prompt. Always return honest status.

## Docstring Example

```python
async def resolve_parameters(
    state: GraphState,
) -> GraphState:
    """Extract and validate tool parameters from user query and context.

    Combines the current user message with existing session context
    to produce a complete set of parameters for tool invocation.
    Implements CMP-05 Parameter Resolver with provenance classification
    (REQUIRED, OPTIONAL, DERIVED, CONTEXT, FORBIDDEN).

    Args:
        state: Current LangGraph state containing user_message,
            context, and routed intent.

    Returns:
        Updated GraphState with resolved_params populated.

    Raises:
        ClarificationNeeded: When REQUIRED params are missing
            from both query and context.
    """
```

## Database

- POI table: relational queries, B-tree + GIN indexes, no embedding
- kb_chunks table: pgvector HNSW + full-text search (hybrid retrieval)
- conversation_log: async audit logging
- Redis: ctx:{session_id} JSON with 30min TTL

## Testing

- pytest + pytest-asyncio
- Unit: mock tool responses, test nodes independently
- Integration: test full graph per UC (UC01, UC02, UC03)
- Regression: golden_set.json (26 cases)

## Commands

```
make up          # Start Docker services
make migrate     # Run Alembic migrations
make seed        # Seed POI + KB data
make test        # Run all tests
make lint        # Ruff linter
make reset       # Full reset
```
