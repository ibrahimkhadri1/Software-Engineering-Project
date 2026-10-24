"""batch owner

Revision ID: 2f04aa94879c
Revises: d6a37ade3008
Create Date: 2026-10-24 14:28:20.894431

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f04aa94879c"
down_revision: str | Sequence[str] | None = "d6a37ade3008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batches made before sign-in existed belong to nobody until the 48 h purge removes them.
    op.add_column("grading_batches", sa.Column("auth0_sub", sa.String(), nullable=False, server_default=""))
    op.alter_column("grading_batches", "auth0_sub", server_default=None)


def downgrade() -> None:
    op.drop_column("grading_batches", "auth0_sub")
