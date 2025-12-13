"""Add script and content_chunk models for RAG

Revision ID: 74130f556607
Revises: c264d90645b4
Create Date: 2025-12-14 00:49:36.257896

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "74130f556607"
down_revision: Union[str, None] = "c264d90645b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create scripts table
    op.create_table(
        "scripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("estimated_duration", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("style_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("hook_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "forbidden_words", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        sa.Column("quality_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("generation_model", sa.String(length=100), nullable=False),
        sa.Column("context_chunks_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "generation_metadata",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generated"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for scripts
    op.create_index("idx_script_channel_status", "scripts", ["channel_id", "status"])
    op.create_index("idx_script_quality", "scripts", ["channel_id", "quality_passed"])
    op.create_index(op.f("ix_scripts_channel_id"), "scripts", ["channel_id"])
    op.create_index(op.f("ix_scripts_quality_passed"), "scripts", ["quality_passed"])
    op.create_index(op.f("ix_scripts_status"), "scripts", ["status"])
    op.create_index(op.f("ix_scripts_topic_id"), "scripts", ["topic_id"])

    # Create content_chunks table
    op.create_table(
        "content_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("script_id", sa.UUID(), nullable=True),
        sa.Column("content_type", sa.String(length=20), nullable=False, server_default="script"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("position", sa.String(length=20), nullable=False),
        sa.Column("context_before", sa.Text(), nullable=True),
        sa.Column("context_after", sa.Text(), nullable=True),
        sa.Column("is_opinion", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_example", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_analogy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("keywords", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("performance_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for content_chunks
    op.create_index("idx_chunk_channel_type", "content_chunks", ["channel_id", "content_type"])
    op.create_index("idx_chunk_characteristics", "content_chunks", ["is_opinion", "is_example"])
    op.create_index("idx_chunk_performance", "content_chunks", ["channel_id", "performance_score"])
    op.create_index(op.f("ix_content_chunks_channel_id"), "content_chunks", ["channel_id"])
    op.create_index(op.f("ix_content_chunks_content_type"), "content_chunks", ["content_type"])
    op.create_index(op.f("ix_content_chunks_is_example"), "content_chunks", ["is_example"])
    op.create_index(op.f("ix_content_chunks_is_opinion"), "content_chunks", ["is_opinion"])
    op.create_index(
        op.f("ix_content_chunks_performance_score"), "content_chunks", ["performance_score"]
    )
    op.create_index(op.f("ix_content_chunks_position"), "content_chunks", ["position"])
    op.create_index(op.f("ix_content_chunks_script_id"), "content_chunks", ["script_id"])

    # Create HNSW index for vector similarity search
    op.execute(
        """
        CREATE INDEX idx_chunk_embedding_hnsw ON content_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("content_chunks")
    op.drop_table("scripts")

    # Note: We don't drop the vector extension as it might be used by other tables
