"""Execution Trace Schema (CMP-11, CMP-12).

Models audit trace records mapped 1-1 to Langfuse traces and spans for regression
evaluation with golden datasets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    """Execution telemetry for a single tool call span."""

    tool_name: str = Field(description="Name of invoked tool")
    tool_input: dict[str, Any] = Field(description="Input parameters passed to tool")
    tool_output: dict[str, Any] = Field(description="Normalized tool response")
    latency_ms: float = Field(default=0.0, description="Execution duration in milliseconds")


class RetrievalSourceTrace(BaseModel):
    """Source reference retrieved from Knowledge Base."""

    chunk_id: str = Field(description="KB Chunk identifier")
    title: str = Field(description="KB Article title")
    score: float = Field(description="RRF retrieval score")


class TraceRecord(BaseModel):
    """Standard execution trace output representing one complete turn processing."""

    run_id: str = Field(description="Unique execution run identifier")
    session_id: str = Field(description="Session identifier")
    bot_version: str = Field(default="V1.0", description="Bot release version")
    dataset_case_id: str | None = Field(default=None, description="Golden test case identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Turn execution timestamp"
    )
    raw_user_input: str = Field(description="Original user prompt string")
    selected_route: str = Field(description="Intent route chosen by Router")
    context_before: dict[str, Any] = Field(description="Context state before this turn")
    context_after: dict[str, Any] = Field(description="Context state after updates")
    tool_calls: list[ToolCallTrace] = Field(default_factory=list, description="Executed tool spans")
    retrieved_sources: list[RetrievalSourceTrace] = Field(
        default_factory=list,
        description="Knowledge base citations",
    )
    final_response: str = Field(description="Final generated reply sent to user")
    e2e_latency_ms: float = Field(default=0.0, description="End-to-end turn latency in ms")
    runtime_status: str = Field(default="OK", description="Execution status ('OK', 'ERROR')")
    error_code: str | None = Field(default=None, description="System error code if any")
