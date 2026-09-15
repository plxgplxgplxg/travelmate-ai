"""Base tool protocol definition following Dependency Inversion Principle (DIP).

Ensures that Tool Orchestrator interacts with tools via a unified contract.
Prepares explicit protocols for read-only query tools and mutation side-effect tools.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolProtocol(Protocol):
    """Unified structural interface for read-only executable tools."""

    name: str
    description: str

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute tool action with the given parameter dictionary.

        Args:
            params: Validated parameter dictionary.

        Returns:
            Normalized dictionary payload adhering to tool response schemas.
        """
        ...


@runtime_checkable
class SideEffectToolProtocol(Protocol):
    """Protocol for tools performing state-mutating actions (e.g. booking, emailing).

    Enforces idempotency and atomic provider execution to prevent duplicate transactions
    under network retry or concurrent request bursts.
    """

    name: str
    description: str

    async def execute(
        self,
        params: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute mutating action using a client-provided idempotency key.

        Architecture Rule:
            Implementations MUST pass idempotency_key directly to the external provider
            or rely on atomic database constraints (e.g. UNIQUE index).
            NEVER use a 'read-then-write' pattern (checking existence before creating),
            as this creates a race condition when two concurrent requests share the same thread_id.

        Args:
            params: Validated parameter dictionary.
            idempotency_key: Client-supplied unique token for deduplication.

        Returns:
            Normalized dictionary response adhering to tool response schemas.
        """
        ...
