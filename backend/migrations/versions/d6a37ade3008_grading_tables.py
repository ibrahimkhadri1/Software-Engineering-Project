"""grading tables

Revision ID: d6a37ade3008
Revises:
Create Date: 2026-10-23 18:57:18.596970

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d6a37ade3008"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "grading_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("assignment_id", sa.String(), nullable=False),
        sa.Column("assignment_name", sa.String(), nullable=False),
        sa.Column("rubric_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "grading_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("assignment_id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("student_name", sa.String(), nullable=False),
        sa.Column("attempt", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("submission_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "READY_FOR_GRADING",
                "BEING_GRADED",
                "AI_ERROR_MANUAL_REVIEW",
                "AWAITING_REVIEW",
                "REJECTED",
                "APPROVED",
                "PUBLISHING",
                "PUBLISH_ERROR_MANUAL_REVIEW",
                "PUBLISHED",
                name="status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("ai_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suggested_score", sa.Numeric(), nullable=True),
        sa.Column("suggested_feedback", sa.Text(), nullable=True),
        sa.Column("final_score", sa.Numeric(), nullable=True),
        sa.Column("final_feedback", sa.Text(), nullable=True),
        sa.Column(
            "review_action",
            sa.Enum("PENDING", "ACCEPTED", "EDITED", "REJECTED", name="reviewaction", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("review_comments", sa.Text(), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["grading_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_grading_results_batch_id"), "grading_results", ["batch_id"], unique=False)
    op.create_index(
        "uq_grading_results_published_submission",
        "grading_results",
        ["course_id", "assignment_id", "student_id", "attempt"],
        unique=True,
        postgresql_where=sa.text("status IN ('PUBLISHING', 'PUBLISHED', 'PUBLISH_ERROR_MANUAL_REVIEW')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_grading_results_published_submission",
        table_name="grading_results",
        postgresql_where=sa.text("status IN ('PUBLISHING', 'PUBLISHED', 'PUBLISH_ERROR_MANUAL_REVIEW')"),
    )
    op.drop_index(op.f("ix_grading_results_batch_id"), table_name="grading_results")
    op.drop_table("grading_results")
    op.drop_table("grading_batches")
    op.drop_table("audit_events")
