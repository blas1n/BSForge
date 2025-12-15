"""Add title_text to scripts table.

Revision ID: add_title_text_001
Revises: 6171e595e298
Create Date: 2025-12-15 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_title_text_001"
down_revision: str | None = "6171e595e298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add title_text column to scripts table."""
    op.add_column(
        "scripts",
        sa.Column("title_text", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    """Remove title_text column from scripts table."""
    op.drop_column("scripts", "title_text")
