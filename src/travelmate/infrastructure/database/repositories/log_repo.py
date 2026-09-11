"""Concrete repository implementation for conversation logging and audit trails.

Stores conversational turns, user messages, assistant replies, and context snapshots
to PostgreSQL using SQLAlchemy 2.0 async.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.travelmate.infrastructure.database.models import ConversationLogModel
from src.travelmate.infrastructure.database.repositories.base import LogRepositoryProtocol

logger = structlog.get_logger(__name__)


class LogRepository(LogRepositoryProtocol):
    """PostgreSQL adapter implementing LogRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active AsyncSession.

        Args:
            session: SQLAlchemy AsyncSession for executing queries.
        """
        self._session = session

    async def log_interaction(
        self,
        session_id: str,
        role: str,
        content: str,
        context_snapshot: dict[str, Any] | None = None,
        intent: str | None = None,
        bot_version: str = "V1.0",
    ) -> None:
        """Record a single interaction turn or agent action.

        Args:
            session_id: Conversation session identifier.
            role: Message sender ('user', 'assistant', 'system').
            content: Raw message text or action summary.
            context_snapshot: Current state snapshot of the conversation.
            intent: Classified intent label if available.
            bot_version: Bot release version tag.
        """
        log_entry = ConversationLogModel(
            session_id=session_id,
            role=role,
            content=content,
            context_snapshot=context_snapshot,
            intent=intent,
            bot_version=bot_version,
        )
        self._session.add(log_entry)
        await self._session.commit()
        logger.debug("Logged conversation interaction", session_id=session_id, role=role, intent=intent)

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[ConversationLogModel]:
        """Fetch chronological interaction history for a given session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of recent log turns.

        Returns:
            List of ConversationLogModel ordered chronologically.
        """
        stmt = (
            select(ConversationLogModel)
            .where(ConversationLogModel.session_id == session_id)
            .order_by(ConversationLogModel.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
