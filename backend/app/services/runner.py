import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.models import AuditEvent, GradingResult
from app.domain.bedrock_val import BedrockVal, BedrockValError, GradeSuggestion
from app.domain.partial_credit import PartialCreditCounter
from app.domain.publish import BACKOFF_SECONDS, PublishAttempt
from app.domain.rubric import RubricStruct, rubric_parser
from app.domain.status import Status, transition
from app.domain.submission import SubmissionError, extract_text
from app.integrations.canvas import Canvas, CanvasError
from app.integrations.grader import AIGrader, GraderError
from app.services.retention import purge_content

log = logging.getLogger(__name__)

MAX_AI_CHARS = 200_000  # cost cap per attempt; the 5 MB file limit allows far more


def _apply_keyword_credit(suggestion: GradeSuggestion, rubric: RubricStruct, text: str) -> None:
    for score, criterion in zip(suggestion.criteria, rubric.criteria, strict=True):
        if criterion.accepted_keywords:
            score.awarded_points = PartialCreditCounter(criterion).add_partialcredit(text)
    suggestion.total = sum((s.awarded_points for s in suggestion.criteria), Decimal(0))


class Runner:
    """Grades and publishes in background tasks; the result's status column is the queue."""

    def __init__(self, sessions: async_sessionmaker, canvas: Canvas, grader: AIGrader, concurrency: int) -> None:
        self.sessions = sessions
        self.canvas = canvas
        self.grader = grader
        self.slots = asyncio.Semaphore(concurrency)
        self.tasks: set[asyncio.Task] = set()

    def grade(self, result_id: uuid.UUID) -> None:
        self._spawn(self._grade, result_id)

    def publish(self, result_id: uuid.UUID) -> None:
        self._spawn(self._publish, result_id)

    async def resume(self) -> None:
        async with self.sessions() as session:
            # Canvas may already hold an interrupted publish, so a person checks it instead of a blind retry.
            await session.execute(
                update(GradingResult).where(GradingResult.status == Status.PUBLISHING)
                .values(status=Status.PUBLISH_ERROR_MANUAL_REVIEW, error="publish interrupted, check Canvas")
            )
            pending = (await session.scalars(select(GradingResult.id).where(
                GradingResult.status.in_([Status.READY_FOR_GRADING, Status.BEING_GRADED])
            ))).all()
            await session.commit()
        for result_id in pending:
            self.grade(result_id)

    def stop(self) -> None:
        for task in self.tasks:
            task.cancel()

    def _spawn(self, work: Callable[[uuid.UUID], Awaitable[None]], result_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._guarded(work, result_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _guarded(self, work: Callable[[uuid.UUID], Awaitable[None]], result_id: uuid.UUID) -> None:
        try:
            async with self.slots:
                await work(result_id)
        # shortcut: the row stays stuck until resume() on restart, add a stale-row sweep if that bites
        except Exception as exc:
            log.error("background task failed", exc_info=exc, extra={"result_id": str(result_id)})

    async def _grade(self, result_id: uuid.UUID) -> None:
        async with self.sessions() as session:
            row = await session.get(GradingResult, result_id, options=[selectinload(GradingResult.batch)])
            if row is None or row.status not in (Status.READY_FOR_GRADING, Status.BEING_GRADED):
                return
            row.status = Status.BEING_GRADED
            await session.commit()
            try:
                if row.submission_text is None:
                    row.submission_text = await self._submission_text(row.attachments)
            except (SubmissionError, CanvasError) as e:
                return await self._fail(session, row, str(e))
            if len(row.submission_text) > MAX_AI_CHARS:
                return await self._fail(session, row, "Submission too long for AI grading")
            rubric = rubric_parser(row.batch.rubric_text)
            validator = BedrockVal(rubric)
            correction = None
            while validator.can_retry:
                try:
                    raw = await self.grader.grade(rubric, row.submission_text, correction)
                except GraderError:
                    raw = None  # a failed call still uses up one of the three attempts
                try:
                    suggestion = validator.validate_output(raw)
                    break
                except BedrockValError as e:
                    if raw is not None:  # a failed call has nothing for the model to correct
                        correction = str(e)
                    elif validator.can_retry:
                        await asyncio.sleep(BACKOFF_SECONDS[validator.retry_attempt - 1])
            else:
                failure = "AI service unavailable" if raw is None else "AI output invalid"
                return await self._fail(session, row, f"{failure} after 3 attempts")
            _apply_keyword_credit(suggestion, rubric, row.submission_text)
            row.ai_output = {
                "criteria": [{"criterion_id": c.criterion_id, "awarded_points": float(c.awarded_points),
                              "rationale": c.rationale, "feedback": c.feedback} for c in suggestion.criteria],
                "warnings": suggestion.warnings,
                "manual_review_required": suggestion.manual_review_required,
            }
            row.suggested_score = suggestion.total
            row.suggested_feedback = suggestion.overall_feedback
            row.status = transition(row.status, Status.AWAITING_REVIEW)
            await session.commit()

    async def _submission_text(self, attachments: list[dict]) -> str:
        parts = []
        for attachment in attachments:
            text = extract_text(attachment["filename"], await self._download(attachment["url"]))
            parts.append(f"--- {attachment['filename']} ---\n{text}")
        return "\n\n".join(parts)

    async def _download(self, url: str) -> bytes:
        for delay in BACKOFF_SECONDS:
            try:
                return await self.canvas.download(url)
            except CanvasError:
                await asyncio.sleep(delay)
        return await self.canvas.download(url)

    async def _fail(self, session: AsyncSession, row: GradingResult, error: str) -> None:
        log.error("grading failed", extra={"result_id": str(row.id)})
        row.status = transition(row.status, Status.AI_ERROR_MANUAL_REVIEW)
        row.error = error
        await session.commit()

    async def _publish(self, result_id: uuid.UUID) -> None:
        async with self.sessions() as session:
            row = await session.get(GradingResult, result_id)
            if row is None or row.status != Status.PUBLISHING:
                return
            attempt = PublishAttempt(row.course_id, row.assignment_id, row.student_id, row.attempt,
                                     row.publish_attempts)
            while not attempt.published:
                try:
                    await self.canvas.publish(row.course_id, row.assignment_id, row.student_id, row.attempt,
                                              row.final_score, row.final_feedback)
                    attempt.successful()
                except CanvasError:
                    delay = attempt.unsuccessful()
                    if delay is None:
                        break
                    await asyncio.sleep(delay)
            row.publish_attempts = attempt.previous_attempts
            if attempt.published:
                row.status = transition(row.status, Status.PUBLISHED)
                row.published_at = datetime.now(UTC)
                purge_content(row)
            else:
                row.status = transition(row.status, Status.PUBLISH_ERROR_MANUAL_REVIEW)
                row.error = "Canvas publish failed after 3 attempts"
                log.error("publish failed", extra={"result_id": str(row.id)})
            session.add(AuditEvent(action=row.status.lower(), batch_id=row.batch_id, result_id=row.id))
            await session.commit()
