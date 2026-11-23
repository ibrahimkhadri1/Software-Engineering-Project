import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.review import ReviewAction
from app.domain.status import Status

# Statuses that hold the one publish slot per submission attempt, across batches (TC-006).
PUBLISH_CLAIMED = (Status.PUBLISHING, Status.PUBLISHED, Status.PUBLISH_ERROR_MANUAL_REVIEW)


class Base(DeclarativeBase):
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        Decimal: Numeric,
        Status: Enum(Status, native_enum=False, length=32),
        ReviewAction: Enum(ReviewAction, native_enum=False, length=16),
    }


class GradingBatch(Base):
    __tablename__ = "grading_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[str]
    assignment_id: Mapped[str]
    assignment_name: Mapped[str]
    rubric_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]

    results: Mapped[list["GradingResult"]] = relationship(back_populates="batch", passive_deletes=True)


class GradingResult(Base):
    __tablename__ = "grading_results"
    __table_args__ = (
        Index(
            "uq_grading_results_published_submission",
            "course_id", "assignment_id", "student_id", "attempt",
            unique=True,
            postgresql_where=text("status IN (" + ", ".join(f"'{s.name}'" for s in PUBLISH_CLAIMED) + ")"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grading_batches.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str]
    assignment_id: Mapped[str]
    student_id: Mapped[str]
    student_name: Mapped[str]
    attempt: Mapped[str]
    file_type: Mapped[str]
    attachments: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    submission_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(default=Status.READY_FOR_GRADING)
    error: Mapped[str | None]
    ai_output: Mapped[dict | None] = mapped_column(JSONB)
    suggested_score: Mapped[Decimal | None]
    suggested_feedback: Mapped[str | None] = mapped_column(Text)
    final_score: Mapped[Decimal | None]
    final_feedback: Mapped[str | None] = mapped_column(Text)
    review_action: Mapped[ReviewAction] = mapped_column(default=ReviewAction.PENDING)
    review_comments: Mapped[str | None] = mapped_column(Text)
    publish_attempts: Mapped[int] = mapped_column(default=0)
    reviewed_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    published_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    batch: Mapped[GradingBatch] = relationship(back_populates="results")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str]
    batch_id: Mapped[uuid.UUID | None]
    result_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
