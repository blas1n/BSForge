"""Replace title_text with headline in scripts table.

This migration:
1. Adds a required 'headline' column (max 30 chars)
2. Removes the 'title_text' column (deprecated)

Revision ID: replace_title_text_with_headline
Revises: consolidate_terms
Create Date: 2025-12-28 13:37:24.052928

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "replace_title_text_with_headline"
down_revision: str | None = "consolidate_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace title_text with headline."""
    # Step 1: Add headline column (temporarily nullable for existing data)
    op.add_column(
        "scripts",
        sa.Column("headline", sa.String(length=30), nullable=True),
    )

    # Step 2: Migrate title_text to headline (or use empty string as default)
    op.execute(
        """
        UPDATE scripts
        SET headline = COALESCE(SUBSTRING(title_text, 1, 30), '')
        """
    )

    # Step 3: Make headline NOT NULL
    op.alter_column("scripts", "headline", nullable=False)

    # Step 4: Drop title_text column
    op.drop_column("scripts", "title_text")


def downgrade() -> None:
    """Restore title_text from headline."""
    # Step 1: Add back title_text column
    op.add_column(
        "scripts",
        sa.Column("title_text", sa.VARCHAR(length=200), nullable=True),
    )

    # Step 2: Copy headline to title_text
    op.execute(
        """
        UPDATE scripts
        SET title_text = headline
        """
    )

    # Step 3: Drop headline column
    op.drop_column("scripts", "headline")
