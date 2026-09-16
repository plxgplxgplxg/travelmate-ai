"""Context Manager Node implementation (CMP-03).

Handles multi-turn conversational context evolution: Retain, Overwrite, Reset,
and Reference Resolution rules across conversation turns.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.context import (
    ContextState,
)

logger = structlog.get_logger(__name__)

# Keywords indicating explicit intent to reset content
RESET_KEYWORDS = [
    "reset",
    "clear",
    "start over",
    "forget",
    "new conversation",
    "new context",
    "bỏ kế hoạch cũ",
    "bỏ hết",
    "làm lại từ đầu",
    "tư vấn lại từ đầu",
    "xóa hết",
    "bắt đầu lại",
    "kế hoạch mới hoàn toàn",
]

# Patterns for ordinal reference resolution (e.g., 'chỗ thứ 2', 'khách sạn thứ nhất')
ORDINAL_PATTERNS = [
    (
        re.compile(
            r"(chỗ|khách sạn|quán|địa điểm)\s+(thứ\s+nhất|đầu\s+tiên|số\s+1|1)", re.IGNORECASE
        ),
        0,
    ),
    (re.compile(r"(chỗ|khách sạn|quán|địa điểm)\s+(thứ\s+hai|thứ\s+2|số\s+2|2)", re.IGNORECASE), 1),
    (re.compile(r"(chỗ|khách sạn|quán|địa điểm)\s+(thứ\s+ba|thứ\s+3|số\s+3|3)", re.IGNORECASE), 2),
]


def check_is_reset(user_input: str) -> bool:
    """Check if the user prompt explicitly requests resetting context

    Args:
        user_input: Raw query string from user.

    Returns:
        True if a reset phrase is detected, False otherwise.
    """
    normalized = user_input.lower().strip()
    return any(keyword in normalized for keyword in RESET_KEYWORDS)


def resolve_reference(user_input: str, last_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve ordinal reference (e.g. 'chỗ thứ 2') against last results.

    Args:
        user_input: Raw query string from user.
        last_results: List of last tool outputs (dicts) to resolve against.

    Returns:
        Referenced entity dictionary if pattern matches and index is valid, otherwise None.
    """
    if not last_results:
        return None

    for pattern, index in ORDINAL_PATTERNS:
        if pattern.search(user_input) and 0 <= index < len(last_results):
            logger.info("Resolved ordinal reference", index=index, target=last_results[index])
            return last_results[index]
    return None


async def context_manager_node(state: TravelMateState) -> dict[str, Any]:
    """Execute the Context Manager node logic within LangGraph StateGraph.

    Evaluates user input for reset directives, merges persistent session state with the incoming turn, and prepares the updated ContextState.

    Args:
        state: Current TravelMateState containing session and turn data.

    Returns:
        Dictionary update for 'context' and initial state fields."""
    session_id = state.get("session_id", "default_session")
    raw_input = state.get("raw_user_input", "")
    existing_ctx = state.get("context", {})

    logger.debug(
        "Running Context Manager Node",
        session_id=session_id,
        input_preview=raw_input[:60],
        existing_context=existing_ctx,
    )

    # Rule BR-UC03-01: Explicit Reset Command
    if check_is_reset(raw_input):
        logger.info("Resetting conversation context upon user request", session_id=session_id)
        new_ctx = ContextState(session_id=session_id)
        return {
            "context": new_ctx.model_dump(),
            "extracted_params": {},
            "grounded_evidence": "",
        }

    # If context is not yet loaded or empty, initialize baseline
    if not existing_ctx.get("session_id"):
        ctx_obj = ContextState(session_id=session_id)
    else:
        ctx_obj = ContextState.model_validate(existing_ctx)

    # Reference Resolution check (e.g., 'chỗ thứ 2')
    last_results = ctx_obj.last_results
    resolved_entity = resolve_reference(raw_input, [item.model_dump() for item in last_results])

    updates: dict[str, Any] = {
        "context": ctx_obj.model_dump(),
        "is_safe": True,
        "error": None,
    }

    if resolved_entity:
        poi_id = resolved_entity.get("id") or resolved_entity.get("poi_id")
        poi_name = resolved_entity.get("name")
        logger.info("Bound referenced entity to context", entity_id=poi_id, entity_name=poi_name)
        updates["extracted_params"] = {
            "target_poi_id": poi_id,
            "target_poi_name": poi_name,
        }

    return updates
