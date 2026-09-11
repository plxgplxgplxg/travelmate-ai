"""Initial database schema with pgvector and indexes.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-11 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create poi table
    op.create_table(
        "poi",
        sa.Column("poi_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Numeric(precision=3, scale=1), server_default="0.0", nullable=False),
        sa.Column("price_numeric", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("price_info", sa.String(length=128), server_default="", nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("source", sa.String(length=128), server_default="deterministic_mock_v1", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=64), server_default="official", nullable=False),
        sa.Column("verified_at", sa.Date(), nullable=True),
        sa.Column("city_alias", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("scope_and_limitations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_poi_location_category", "poi", ["location", "category"])
    op.create_index("idx_poi_price", "poi", ["price_numeric"])
    op.create_index("idx_poi_attributes", "poi", ["attributes"], postgresql_using="gin")

    # 3. Create kb_chunks table
    op.create_table(
        "kb_chunks",
        sa.Column("chunk_id", sa.String(length=64), primary_key=True),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.VECTOR(768), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("source", sa.String(length=128), server_default="knowledge_base_v1", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=64), server_default="official", nullable=False),
        sa.Column("data_version", sa.String(length=64), server_default="kb_v1.0", nullable=False),
        sa.Column("city_alias", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("scope_and_limitations", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_updated", sa.Date(), nullable=True),
        sa.Column("content_tsvector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "idx_kb_embedding",
        "kb_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("idx_kb_content_fts", "kb_chunks", ["content_tsvector"], postgresql_using="gin")
    op.create_index("idx_kb_category_location", "kb_chunks", ["category", "location"])
    op.create_index("idx_kb_is_active", "kb_chunks", ["is_active"])

    # 4. Create conversation_log table
    op.create_table(
        "conversation_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("bot_version", sa.String(length=32), server_default="V1.0", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_conversation_session", "conversation_log", ["session_id"])
    op.create_index("idx_conversation_created_at", "conversation_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("conversation_log")
    op.drop_table("kb_chunks")
    op.drop_table("poi")
    op.execute("DROP EXTENSION IF EXISTS vector;")
