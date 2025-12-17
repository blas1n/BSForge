"""Add BM25 search index for hybrid RAG

Revision ID: add_bm25_search
Revises: 6171e595e298
Create Date: 2025-12-17 12:42:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_bm25_search"
down_revision: str | None = "6171e595e298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pg_search extension (ParadeDB BM25)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # Create BM25 index on content_chunks.keywords array
    # ParadeDB uses CREATE INDEX ... USING bm25 syntax
    op.execute(
        """
        CREATE INDEX idx_chunks_bm25 ON content_chunks
        USING bm25 (id, keywords)
        WITH (key_field='id')
        """
    )


def downgrade() -> None:
    # Drop BM25 index
    op.execute("DROP INDEX IF EXISTS idx_chunks_bm25")

    # Note: We don't drop pg_search extension as it might be used elsewhere
