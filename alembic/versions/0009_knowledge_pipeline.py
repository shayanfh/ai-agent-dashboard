"""Add knowledge document ingestion, chunks, and cache versioning.

Revision ID: 0009_knowledge_pipeline
Revises: 0008_employee_extensions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_knowledge_pipeline"
down_revision: str | None = "0008_employee_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("knowledge_version", sa.BigInteger(), server_default="1", nullable=False),
    )
    op.add_column("knowledge_documents", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_documents", sa.Column("content_type", sa.String(100), nullable=True)
    )
    op.add_column("knowledge_documents", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_knowledge_chunks_company_agent",
        "knowledge_chunks",
        ["company_id", "agent_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_document",
        "knowledge_chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_document", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_company_agent", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_column("knowledge_documents", "processed_at")
    op.drop_column("knowledge_documents", "error_message")
    op.drop_column("knowledge_documents", "size_bytes")
    op.drop_column("knowledge_documents", "content_type")
    op.drop_column("knowledge_documents", "storage_key")
    op.drop_column("companies", "knowledge_version")
