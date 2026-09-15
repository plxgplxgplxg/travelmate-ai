"""FastAPI Application entrypoint with modern lifespan management.

Manages connection pools for PostgreSQL (pgvector), Redis 7, Langfuse observability,
CORS middleware, and health checking endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.travelmate.config import settings
from src.travelmate.infrastructure.database.session import close_db, init_db, ping_db
from src.travelmate.infrastructure.redis.client import close_redis, init_redis, ping_redis
from src.travelmate.observability.logger import configure_logging
from src.travelmate.observability.tracer import flush_langfuse, init_langfuse

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and graceful shutdown for shared infrastructure pools.

    Args:
        app: FastAPI application instance.

    Yields:
        Control back to the ASGI server runtime.
    """
    # Startup Phase
    configure_logging()
    logger.info(
        "Starting TravelMate AI service",
        version=settings.bot_version,
        env=settings.app_env,
    )

    try:
        await init_db()
        await init_redis()
        init_langfuse()
        logger.info("All infrastructure connection pools successfully initialized")
    except Exception as exc:
        logger.error("Error during startup initialization", error=str(exc))
        raise

    yield

    # Shutdown Phase
    logger.info("Initiating graceful shutdown of TravelMate AI service")
    flush_langfuse()
    await close_redis()
    await close_db()
    logger.info("Teardown complete. Service stopped")


def create_app() -> FastAPI:
    """Application factory creating configured FastAPI app.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="TravelMate AI API",
        description="Vietnamese travel assistant chatbot orchestrating LangGraph, pgvector, and Redis",
        version=settings.bot_version,
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["System"])
    async def health_check() -> JSONResponse:
        """Health check endpoint probing database and Redis pools.

        Returns:
            JSON response detailing service and component health states.
        """
        db_ok = await ping_db()
        redis_ok = await ping_redis()
        is_healthy = db_ok and redis_ok

        status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if is_healthy else "degraded",
                "database": db_ok,
                "redis": redis_ok,
                "version": settings.bot_version,
            },
        )

    @app.get("/version", tags=["System"])
    async def version_info() -> dict[str, str]:
        """Return frozen version tags for regression validation.

        Returns:
            Dictionary containing bot version and system prompt version.
        """
        return {
            "bot_version": settings.bot_version,
            "system_prompt_version": settings.system_prompt_version,
            "environment": settings.app_env,
        }

    return app


app = create_app()
