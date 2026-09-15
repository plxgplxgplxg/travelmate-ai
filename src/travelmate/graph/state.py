"""LangGraph State schema definition for TravelMate AI.

Defines the shared state dictionary passed across all workflow nodes in the
deterministic StateGraph orchestration pipeline. Supports cyclic tool loop
via Annotated reducers for accumulative fields.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class TravelMateState(TypedDict, total=False):
    """Global state flowing through the LangGraph StateGraph.

    Fields using Annotated[..., operator.add] are accumulative — each node
    returns NEW items only, and LangGraph automatically appends them to
    the existing list. This enables the cyclic tool loop to accumulate
    results across multiple iterations.

    Attributes:
        session_id: Unique identifier for the user session (also serves as thread_id
            for LangGraph AsyncPostgresSaver checkpoint persistence).
        raw_user_input: Raw string message received in the current turn.
        current_intent: Intent predicted by Router ('UC01_FIND_PLACE', etc.).
        context: Active ContextState dictionary representation (Business Context).
        extracted_params: Validated parameters resolved by Parameter Resolver.
        tool_outputs: Accumulated raw outputs from all tool executions across
            loop iterations. Uses operator.add reducer for append semantics.
        evidence: Normalized list of Evidence dicts (schemas/evidence.py).
        grounded_evidence: Formatted textual facts passed to Response Generator.
        final_response: Generated assistant response string.
        is_safe: Flag set by Safety Guard indicating input/output compliance.
        error: System error code or message if an execution failure occurs.
        turn_count: Interaction turn counter for this session.
        tool_iterations: Counter tracking how many tool loop cycles have executed.
        pending_intents: Sub-intents detected by Resolver that need tool coverage
            (e.g. ["ACCOM", "FOOD"] for compound queries).
        completed_tools: Tool+category keys already executed in this turn
            (e.g. ["poi_search:ACCOM"]). Uses operator.add reducer.
        needs_more_tools: Flag set by Tool Evaluator indicating whether the loop
            should continue back to Tool Orchestrator.
        kb_fallback_needed: Flag set by Tool Evaluator indicating whether
            knowledge_search should be triggered as fallback for EMPTY results.
        confidence: Confidence score of intent classification or routing (0.0 to 1.0).
        idempotency_key: Optional UUID string passed from Client/API for mutation
            operations (reserved for Phase 4+ side-effect tools).
    """

    session_id: str
    raw_user_input: str
    current_intent: str
    confidence: float | None
    context: dict[str, Any]
    extracted_params: dict[str, Any]
    tool_outputs: Annotated[list[dict[str, Any]], operator.add]
    evidence: list[dict[str, Any]]
    grounded_evidence: str
    final_response: str
    is_safe: bool
    error: str | None
    turn_count: int
    tool_iterations: int
    pending_intents: list[str]
    completed_tools: Annotated[list[str], operator.add]
    needs_more_tools: bool
    kb_fallback_needed: bool
    idempotency_key: str | None
