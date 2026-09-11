"""Langfuse Observability Client Abstraction (CMP-11, CMP-12).

Wraps the Langfuse Python SDK behind a decoupled tracer client protocol,
supporting distributed tracing, generation spans, and graceful flush.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
import structlog

from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


@runtime_checkable
class TracerClientProtocol(Protocol):
    """Structural interface for observability and distributed tracing."""

    def trace(self, name: str, session_id: str, metadata: dict[str, Any] | None = None) -> Any:
        """Create or update a root trace span."""
        ...

    def flush(self) -> None:
        """Flush pending telemetry events to the observability server."""
        ...


class LangfuseClientWrapper(TracerClientProtocol):
    """Concrete wrapper around the Langfuse SDK."""

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None:
        self.public_key = public_key or settings.langfuse_public_key
        self.secret_key = secret_key or settings.langfuse_secret_key
        self.host = host or settings.langfuse_host
        self._langfuse: Any = None
        self._init_sdk()

    def _init_sdk(self) -> None:
        if self.public_key and self.secret_key:
            try:
                from langfuse import Langfuse
                self._langfuse = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                )
                logger.info("Langfuse SDK successfully initialized", host=self.host)
            except Exception as exc:
                logger.warning("Failed initializing Langfuse SDK", error=str(exc))
                self._langfuse = None
        else:
            logger.info("Langfuse credentials not set, telemetry will run in local-only mode")

    def trace(self, name: str, session_id: str, metadata: dict[str, Any] | None = None) -> Any:
        """Create a new Langfuse trace if SDK is active."""
        if self._langfuse is not None:
            try:
                return self._langfuse.trace(
                    name=name,
                    session_id=session_id,
                    metadata=metadata or {},
                )
            except Exception as exc:
                logger.debug("Failed creating Langfuse trace", error=str(exc))
        return None

    def flush(self) -> None:
        """Flush telemetry events before process exit."""
        if self._langfuse is not None:
            try:
                self._langfuse.flush()
                logger.debug("Flushed Langfuse telemetry")
            except Exception as exc:
                logger.warning("Error flushing Langfuse client", error=str(exc))


_global_tracer_client: TracerClientProtocol | None = None


def get_tracer_client() -> TracerClientProtocol:
    """Retrieve global tracer client singleton."""
    global _global_tracer_client
    if _global_tracer_client is None:
        _global_tracer_client = LangfuseClientWrapper()
    return _global_tracer_client
