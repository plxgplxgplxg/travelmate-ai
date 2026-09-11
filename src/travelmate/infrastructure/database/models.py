"""SQLAlchemy 2.0 declarative database models for TravelMate AI.

Defines schemas and indexes for:
- poi: Relational point of interest storage (hotels, restaurants, attractions).
- kb_chunks: Embedded knowledge base chunks for hybrid retrieval (dense + lexical).
- conversation_log: Audit trail and multi-turn interaction logs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
import uuid

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy entities."""
    pass


class PoiModel(Base):
    """Database entity representing a point of interest (POI).

    Stores relational data for accommodations, food, and attractions.
    Queried via structured SQL filters in PoiRepository.
    """

    __tablename__ = "poi"

    poi_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 1), default=0.0)
    price_numeric: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    price_info: Mapped[str] = mapped_column(String(128), default="")
    attributes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(128), default="deterministic_mock_v1")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), default="official")
    verified_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    city_alias: Mapped[list[str]] = mapped_column(JSONB, default=list)
    scope_and_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_poi_location_category", "location", "category"),
        Index("idx_poi_price", "price_numeric"),
        Index("idx_poi_attributes", "attributes", postgresql_using="gin"),
    )


class KbChunkModel(Base):
    """Database entity representing an embedded knowledge base chunk.

    Stores document text, metadata, dense embedding vector (768d),
    and lexical tsvector for hybrid search.
    """

    __tablename__ = "kb_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(128), default="knowledge_base_v1")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), default="official")
    data_version: Mapped[str] = mapped_column(String(64), default="kb_v1.0")
    city_alias: Mapped[list[str]] = mapped_column(JSONB, default=list)
    scope_and_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_updated: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_tsvector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_kb_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_kb_content_fts", "content_tsvector", postgresql_using="gin"),
        Index("idx_kb_category_location", "category", "location"),
        Index("idx_kb_is_active", "is_active"),
    )


class ConversationLogModel(Base):
    """Database entity representing conversational turns and audit traces.

    Stores multi-turn user messages, assistant replies, context state
    snapshots, and predicted intents for analytics and regression evaluation.
    """

    __tablename__ = "conversation_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_version: Mapped[str | None] = mapped_column(String(32), default="V1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_conversation_session", "session_id"),
        Index("idx_conversation_created_at", "created_at"),
    )
