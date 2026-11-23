import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import User
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import PUBLISH_CLAIMED, AuditEvent, GradingBatch, GradingResult
from app.db.session import Session
from app.domain.pdf import PdfError, pdf_text
from app.domain.publish import DuplicatePublishError, PublishAttempt, PublishError
from app.domain.review import PredictionAcceptStatus, ReviewError
from app.domain.rubric import RubricError, RubricStruct, rubric_parser
from app.domain.status import Status, transition
from app.domain.submission import SubmissionError, SubmissionStatus, extract_text

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/grading")

# Dashboard counts (SFDS C1).
COUNT_GROUPS = {
    "pending_ai": {Status.READY_FOR_GRADING, Status.BEING_GRADED},
    "ready_for_review": {Status.AWAITING_REVIEW, Status.REJECTED},
    "approved": {Status.APPROVED, Status.PUBLISHING, Status.PUBLISHED},
    "failed": {Status.AI_ERROR_MANUAL_REVIEW, Status.PUBLISH_ERROR_MANUAL_REVIEW},
}
REVIEWABLE = {Status.AWAITING_REVIEW, Status.REJECTED, Status.AI_ERROR_MANUAL_REVIEW}
RUBRIC_PDF_BYTES = 5_000_000


class RubricIn(BaseModel):
    rubric_text: str = Field(max_length=50_000)


class BatchIn(RubricIn):
    course_id: str
    assignment_id: str


class ReviewIn(BaseModel):
    action: Literal["accept", "edit", "reject", "manual"]
    score: Decimal | None = Field(None, allow_inf_nan=False)
    feedback: str | None = Field(None, max_length=10_000)
    comments: str = Field("", max_length=10_000)


class PublishIn(BaseModel):
    result_ids: list[uuid.UUID] = Field(max_length=500)


def _not_found() -> AppError:
    return AppError("NOT_FOUND", "Not found.", 404)


def _parse_rubric(text: str) -> RubricStruct:
    try:
        return rubric_parser(text.replace("\x00", ""))
    except RubricError as e:
        raise AppError("RUBRIC_INVALID", f"The rubric could not be parsed: {e}.", 422) from e


def _criteria(rubric: RubricStruct) -> list[dict]:
    return [{"criterion_id": c.criterion_id, "title": c.title, "description": c.description,
             "max_points": c.max_points, "keywords": c.accepted_keywords} for c in rubric.criteria]


@router.post("/rubric/preview")
async def preview_rubric(body: RubricIn):
    rubric = _parse_rubric(body.rubric_text)
    return {"criteria": _criteria(rubric), "max_score": rubric.max_score}


@router.post("/rubric/pdf")
async def rubric_from_pdf(request: Request):
    data = await request.body()
    if len(data) > RUBRIC_PDF_BYTES:
        raise AppError("RUBRIC_TOO_LARGE", "The rubric PDF must be 5 MB or smaller.", 413)
    try:
        return {"rubric_text": pdf_text(data)}
    except PdfError as e:
        raise AppError("RUBRIC_INVALID", f"The rubric PDF could not be read: {e}.", 422) from e


@router.post("/batches", status_code=202)
async def create_batch(body: BatchIn, request: Request, session: Session, user: User):
    canvas = request.app.state.canvas
    assignment = next((a for a in await canvas.assignments(body.course_id) if a.id == body.assignment_id), None)
    if assignment is None:
        raise _not_found()
    if not assignment.supported:
        raise AppError("ASSIGNMENT_UNSUPPORTED", "This assignment's submission type cannot be graded here.", 422)
    rubric = _parse_rubric(body.rubric_text)
    if rubric.max_score != assignment.points_possible:
        raise AppError("RUBRIC_POINTS_MISMATCH", f"The rubric totals {rubric.max_score} points but the assignment "
                       f"is worth {assignment.points_possible}.", 422)

    batch = GradingBatch(
        auth0_sub=user, course_id=body.course_id, assignment_id=body.assignment_id, assignment_name=assignment.name,
        rubric_text=rubric.raw_text,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().data_ttl_hours),
    )
    for sub in await canvas.submissions(body.course_id, body.assignment_id):
        check = SubmissionStatus.for_submission([a.filename for a in sub.attachments], sub.body)
        accepted, error, text = check.is_accepted, check.error, None
        if accepted and not sub.attachments:  # online text gets the same size limit as files
            try:
                text = extract_text("online_text.txt", sub.body.encode())
            except SubmissionError as e:
                accepted, error = False, str(e)
        batch.results.append(GradingResult(
            course_id=body.course_id, assignment_id=body.assignment_id, student_id=sub.student_id,
            student_name=sub.student_name, attempt=sub.attempt, file_type=check.file_type,
            attachments=[asdict(a) for a in sub.attachments], submission_text=text,
            status=Status.READY_FOR_GRADING if accepted else Status.AI_ERROR_MANUAL_REVIEW, error=error,
        ))
    session.add(batch)
    await session.flush()
    session.add(AuditEvent(action="batch_created", batch_id=batch.id))
    await session.commit()
    for result in batch.results:
        if result.status == Status.READY_FOR_GRADING:
            request.app.state.runner.grade(result.id)
        else:
            log.warning("submission not accepted", extra={"result_id": str(result.id)})
    return {"batch_id": batch.id}


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: uuid.UUID, session: Session, user: User):
    batch = await session.get(GradingBatch, batch_id, options=[selectinload(GradingBatch.results)])
    if batch is None or batch.auth0_sub != user:
        raise _not_found()
    results = sorted(batch.results, key=lambda r: r.student_name)
    return {
        "id": batch.id, "course_id": batch.course_id, "assignment_id": batch.assignment_id,
        "assignment_name": batch.assignment_name, "expires_at": batch.expires_at,
        "max_score": rubric_parser(batch.rubric_text).max_score,
        "counts": {"total": len(results)} | {k: sum(r.status in g for r in results) for k, g in COUNT_GROUPS.items()},
        "results": [{
            "id": r.id, "student_name": r.student_name, "file_type": r.file_type, "status": r.status,
            "suggested_score": r.suggested_score, "final_score": r.final_score, "error": r.error,
        } for r in results],
    }


async def _result(session: AsyncSession, result_id: uuid.UUID, user: str, lock: bool = False) -> GradingResult:
    result = await session.get(GradingResult, result_id, options=[selectinload(GradingResult.batch)],
                               with_for_update=lock)
    if result is None or result.batch.auth0_sub != user:
        raise _not_found()
    return result


@router.get("/results/{result_id}")
async def get_result(result_id: uuid.UUID, session: Session, user: User):
    r = await _result(session, result_id, user)
    rubric = rubric_parser(r.batch.rubric_text)
    return {
        "id": r.id, "batch_id": r.batch_id, "student_name": r.student_name, "attempt": r.attempt,
        "file_type": r.file_type, "status": r.status, "error": r.error, "submission_text": r.submission_text,
        "criteria": _criteria(rubric),
        "max_score": rubric.max_score, "ai_output": r.ai_output,
        "suggested_score": r.suggested_score, "suggested_feedback": r.suggested_feedback,
        "final_score": r.final_score, "final_feedback": r.final_feedback,
        "review_action": r.review_action, "review_comments": r.review_comments,
    }


@router.patch("/results/{result_id}/review")
async def review_result(result_id: uuid.UUID, body: ReviewIn, session: Session, user: User):
    r = await _result(session, result_id, user, lock=True)
    if r.status not in REVIEWABLE:
        raise AppError("INVALID_STATE", "This result can no longer be reviewed.", 409)
    review = PredictionAcceptStatus(
        rubric_parser(r.batch.rubric_text).max_score, r.suggested_score, r.suggested_feedback,
        r.final_score, r.final_feedback, r.review_comments or "", r.review_action,
    )
    try:
        if body.action == "accept":
            review.accept_prediction()
        elif body.action == "reject":
            review.reject_prediction(body.comments)
        elif body.score is None:
            raise ReviewError("a score is required")
        elif body.action == "edit":
            review.edit_prediction(body.score, body.feedback)
        else:
            review.manual_grade(body.score, body.feedback)
        new_status = Status.REJECTED if body.action == "reject" else Status.AWAITING_REVIEW
        if r.status != new_status:
            r.status = transition(r.status, new_status)
    except ReviewError as e:
        raise AppError("REVIEW_INVALID", f"{str(e).capitalize()}.", 422) from e
    r.final_score, r.final_feedback = review.final_score, review.final_feedback
    r.review_comments, r.review_action = review.comments, review.validation_status
    r.reviewed_at = datetime.now(UTC)
    session.add(AuditEvent(action=f"review_{body.action}", batch_id=r.batch_id, result_id=r.id))
    await session.commit()
    return await get_result(result_id, session, user)


@router.post("/batches/{batch_id}/approve-and-publish")
async def approve_and_publish(batch_id: uuid.UUID, body: PublishIn, request: Request, session: Session, user: User):
    batch = await session.get(GradingBatch, batch_id)
    if batch is None or batch.auth0_sub != user:
        raise _not_found()
    outcomes = []
    for result_id in body.result_ids:
        outcome = await _approve_and_claim(session, batch_id, result_id)
        if outcome["ok"]:
            await session.commit()
            request.app.state.runner.publish(result_id)
        else:
            await session.rollback()
        outcomes.append({"result_id": result_id} | outcome)
    return {"outcomes": outcomes}


async def _approve_and_claim(session: AsyncSession, batch_id: uuid.UUID, result_id: uuid.UUID) -> dict:
    r = await session.get(GradingResult, result_id, with_for_update=True)
    if r is None or r.batch_id != batch_id:
        return {"ok": False, "code": "NOT_FOUND", "message": "Result not found."}
    now = datetime.now(UTC)
    if r.status == Status.AWAITING_REVIEW and r.final_score is not None:
        r.status, r.approved_at = transition(r.status, Status.APPROVED), now
        session.add(AuditEvent(action="approved", batch_id=batch_id, result_id=r.id))
    claimed = await session.execute(
        select(GradingResult.course_id, GradingResult.assignment_id, GradingResult.student_id, GradingResult.attempt)
        .where(GradingResult.course_id == r.course_id, GradingResult.assignment_id == r.assignment_id,
               GradingResult.student_id == r.student_id, GradingResult.status.in_(PUBLISH_CLAIMED))
    )
    try:
        PublishAttempt(r.course_id, r.assignment_id, r.student_id, r.attempt, r.publish_attempts).begin(
            r.status, {tuple(key) for key in claimed})
    except DuplicatePublishError:
        return {"ok": False, "code": "DUPLICATE_PUBLISH",
                "message": "This submission was already sent to Canvas, or is waiting for a manual check."}
    except PublishError:
        return {"ok": False, "code": "NOT_REVIEWED", "message": "Review this result before publishing."}
    r.status = transition(r.status, Status.PUBLISHING)
    return {"ok": True}
