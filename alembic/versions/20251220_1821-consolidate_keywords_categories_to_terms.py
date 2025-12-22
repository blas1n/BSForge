"""Consolidate keywords and categories to terms.

This migration unifies the separate 'categories' and 'keywords' columns
into a single 'terms' column in the topics table, and renames 'keywords'
to 'terms' in the content_chunks table.

Revision ID: consolidate_terms
Revises: add_bm25_search_index
Create Date: 2024-12-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "consolidate_terms"
down_revision: str | None = "add_bm25_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Consolidate categories and keywords into terms."""
    # ==========================================================================
    # Topics table: Merge categories + keywords -> terms
    # ==========================================================================

    # Step 1: Add new 'terms' column
    op.add_column(
        "topics",
        sa.Column(
            "terms",
            postgresql.ARRAY(sa.String()),
            nullable=True,  # Temporarily nullable for migration
        ),
    )

    # Step 2: Populate terms by combining categories and keywords (deduped)
    # Using raw SQL for array concatenation and deduplication
    op.execute(
        """
        UPDATE topics
        SET terms = (
            SELECT ARRAY(
                SELECT DISTINCT unnest(
                    COALESCE(categories, ARRAY[]::varchar[]) ||
                    COALESCE(keywords, ARRAY[]::varchar[])
                )
            )
        )
    """
    )

    # Step 3: Make terms NOT NULL now that it's populated
    op.alter_column("topics", "terms", nullable=False)

    # Step 4: Drop old columns
    op.drop_column("topics", "categories")
    op.drop_column("topics", "keywords")

    # ==========================================================================
    # Content_chunks table: Rename keywords -> terms
    # ==========================================================================

    # Step 1: Drop BM25 index that references 'keywords' column
    op.execute("DROP INDEX IF EXISTS idx_chunks_bm25")

    # Step 2: Rename column
    op.alter_column(
        "content_chunks",
        "keywords",
        new_column_name="terms",
    )

    # Step 3: Recreate BM25 index with new column name
    op.execute(
        """
        CREATE INDEX idx_chunks_bm25 ON content_chunks
        USING bm25 (id, terms)
        WITH (key_field='id')
        """
    )


def downgrade() -> None:
    """Restore categories and keywords from terms."""
    # ==========================================================================
    # Content_chunks table: Rename terms -> keywords
    # ==========================================================================

    # Step 1: Drop BM25 index that references 'terms' column
    op.execute("DROP INDEX IF EXISTS idx_chunks_bm25")

    # Step 2: Rename column back
    op.alter_column(
        "content_chunks",
        "terms",
        new_column_name="keywords",
    )

    # Step 3: Recreate BM25 index with original column name
    op.execute(
        """
        CREATE INDEX idx_chunks_bm25 ON content_chunks
        USING bm25 (id, keywords)
        WITH (key_field='id')
        """
    )

    # ==========================================================================
    # Topics table: Split terms -> categories + keywords
    # ==========================================================================

    # Step 1: Add back categories and keywords columns
    op.add_column(
        "topics",
        sa.Column(
            "categories",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
    )

    # Step 2: Copy terms to both columns (best effort - original split unknown)
    op.execute(
        """
        UPDATE topics
        SET categories = terms,
            keywords = terms
    """
    )

    # Step 3: Make columns NOT NULL
    op.alter_column("topics", "categories", nullable=False)
    op.alter_column("topics", "keywords", nullable=False)

    # Step 4: Drop terms column
    op.drop_column("topics", "terms")
