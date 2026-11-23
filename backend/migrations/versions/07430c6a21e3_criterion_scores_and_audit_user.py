"""criterion scores and audit user

Revision ID: 07430c6a21e3
Revises: 2f04aa94879c
Create Date: 2026-11-22 20:40:49.994445

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "07430c6a21e3"
down_revision: str | Sequence[str] | None = "2f04aa94879c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("auth0_sub", sa.String(), nullable=True))
    op.add_column("grading_results", sa.Column("final_criteria", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("grading_results", "final_criteria")
    op.drop_column("audit_events", "auth0_sub")
