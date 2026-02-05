"""add_youtube_metadata_to_scripts

Revision ID: 9f679109b2c8
Revises: b46978c57b8c
Create Date: 2026-02-05 03:18:30.115872

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f679109b2c8"
down_revision: Union[str, None] = "b46978c57b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scripts",
        sa.Column(
            "youtube_title", sa.String(length=100), nullable=True, comment="YouTube video title"
        ),
    )
    op.add_column(
        "scripts",
        sa.Column(
            "youtube_description", sa.Text(), nullable=True, comment="YouTube video description"
        ),
    )
    op.add_column(
        "scripts",
        sa.Column(
            "youtube_tags",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="YouTube video tags",
        ),
    )


def downgrade() -> None:
    op.drop_column("scripts", "youtube_tags")
    op.drop_column("scripts", "youtube_description")
    op.drop_column("scripts", "youtube_title")
