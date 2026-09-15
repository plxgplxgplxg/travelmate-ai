"""Langfuse distributed tracing and observability wrapper (CMP-11).

Provides telemetry tracking, execution latency measurement, and graceful flushing
for LangGraph nodes and tool executions using clients.langfuse_client.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from src.travelmate.clients.langfuse_client import get_tracer_client

logger = structlog.get_logger(__name__)


def init_langfuse() -> Any:
    """Initialize Langfuse tracer client."""
    client = get_tracer_client()
    return client


def get_langfuse() -> Any:
    """Get active Langfuse client wrapper."""
    return get_tracer_client()


def flush_langfuse() -> None:
    """Flush pending telemetry events to Langfuse server before process termination."""
    client = get_tracer_client()
    client.flush()


def observe_step(name: str | None = None) -> Callable:
    """Decorator for tracing workflow steps with Langfuse observe decorator."""
    try:
        from langfuse.decorators import observe

        return observe(name=name)
    except ImportError:

        def decorator(func: Callable) -> Callable:
            return func

        return decorator
