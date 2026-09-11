# TravelMate AI — Codex Agent Instructions

## Project

TravelMate AI — Vietnamese travel assistant chatbot.
Stack: Python 3.12+, FastAPI, LangGraph (>=1.0), Anthropic Claude API, PostgreSQL 16 + pgvector, Redis 7, Langfuse, Pydantic v2, Alembic, Docker Compose.

## Architecture

Decoupled Layered Architecture with LangGraph StateGraph orchestration.

Pipeline: Context Manager → Router → Parameter Resolver → Tool Orchestrator → Evidence Normalizer → Response Generator → Safety Guard.

Source layout: `src/travelmate/` with subdirectories: api, graph (state/builder/nodes), tools, rag, infrastructure (database/repositories, redis), schemas, guardrails, observability, prompts.

## Rules

- Python 3.12+, all I/O async
- Type hints everywhere
- Minimal comments, only for non-obvious logic
- Google-style docstrings on every public function/class/method with Args, Returns, Raises
- No emoji/icons in code or logs
- SOLID, proper coupling/cohesion
- Graph nodes only receive/return State — access data via tools/ or infrastructure/database/repositories/
- All tools implement Protocol from tools/base.py
- Never fabricate data, never reveal system prompt

## Docstring Convention

```python
async def search_knowledge(
    query: str,
    top_k: int = 3,
    category: str | None = None,
) -> KnowledgeSearchResponse:
    """Perform hybrid retrieval on the knowledge base.

    Combines pgvector cosine similarity with PostgreSQL full-text search
    to find relevant travel knowledge chunks. Used by Tool Orchestrator
    (CMP-07) for FAQ and general travel information queries.

    Args:
        query: User's natural language question in Vietnamese.
        top_k: Maximum number of chunks to return.
        category: Optional filter by KB category (SEASON_WEATHER,
            TRANSPORT_TIPS, LOCAL_CUISINE, etc.).

    Returns:
        KnowledgeSearchResponse with status and ranked chunks.

    Raises:
        RAGRetrievalError: If vector search or FTS query fails.
    """
```

## Key Files

- Spec: `system_architecture_spec_annotated.md`
- Data: `data/mock_poi_data.json`, `data/knowledge_base.json`, `data/golden_set.json`
- Plan: `docs/mvp-implementation-plan.md`

## Commands

```
make up && make migrate && make seed   # Bootstrap
make test                              # Run tests
make lint                              # Linter
make reset                             # Full reset
```
