import asyncio
import time
from decimal import Decimal

import pytest
from conftest import RUBRIC_TEXT, add_result
from sqlalchemy import select

from app.db.models import AuditEvent, GradingResult
from app.domain.rubric import rubric_parser
from app.domain.status import Status
from app.integrations.canvas import CanvasError
from app.integrations.fakes import FakeCanvas, FakeGrader
from app.integrations.grader import GraderError
from app.services.runner import Runner

pytestmark = pytest.mark.anyio


class ScriptedGrader:
    def __init__(self, *outputs) -> None:
        self.outputs = list(outputs)
        self.corrections = []

    async def grade(self, rubric, submission_text, correction):
        self.corrections.append(correction)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


async def valid_output():
    return await FakeGrader().grade(rubric_parser(RUBRIC_TEXT), "a loop", None)


async def load(sessions, result_id) -> GradingResult:
    async with sessions() as session:
        return await session.get(GradingResult, result_id)


async def test_valid_output_moves_the_result_to_review(sessions):
    result_id = await add_result(sessions, submission_text="uses a loop and recursion")
    await Runner(sessions, FakeCanvas(), FakeGrader(), 1)._grade(result_id)
    row = await load(sessions, result_id)
    assert row.status == Status.AWAITING_REVIEW
    assert row.suggested_score == Decimal(19)
    assert [c["awarded_points"] for c in row.ai_output["criteria"]] == [10, 5, 4]


async def test_three_invalid_outputs_end_in_manual_review(sessions, caplog):
    """TC-008: three invalid model outputs, no fourth call, no score."""
    result_id = await add_result(sessions, submission_text="answer")
    grader = ScriptedGrader({}, {"schema_version": "1.0"}, [])
    await Runner(sessions, FakeCanvas(), grader, 1)._grade(result_id)
    row = await load(sessions, result_id)
    assert row.status == Status.AI_ERROR_MANUAL_REVIEW
    assert row.error == "AI output invalid after 3 attempts"
    assert row.suggested_score is None
    assert grader.corrections == [None, "unexpected schema version", "criteria missing"]
    assert [r.result_id for r in caplog.records if r.message == "grading failed"] == [str(result_id)]


async def test_a_failed_call_uses_an_attempt_and_backs_off(sessions, monkeypatch):
    monkeypatch.setattr("app.services.runner.BACKOFF_SECONDS", (0.2, 0))
    result_id = await add_result(sessions, submission_text="answer")
    grader = ScriptedGrader(GraderError(), await valid_output())
    start = time.perf_counter()
    await Runner(sessions, FakeCanvas(), grader, 1)._grade(result_id)
    assert time.perf_counter() - start >= 0.2
    assert (await load(sessions, result_id)).status == Status.AWAITING_REVIEW
    assert grader.corrections == [None, None]


async def test_attachments_are_joined_with_their_filenames(sessions):
    files = [{"filename": "lab3.py", "url": "fake://files/lab3.py"},
             {"filename": "essay.pdf", "url": "fake://files/essay.pdf"}]
    result_id = await add_result(sessions, attachments=files)
    await Runner(sessions, FakeCanvas(), FakeGrader(), 1)._grade(result_id)
    text = (await load(sessions, result_id)).submission_text
    assert text.startswith("--- lab3.py ---\ndef factorial")
    assert "\n\n--- essay.pdf ---\nLab 3 write-up" in text


@pytest.mark.parametrize("attachment, error", [
    ({"filename": "gone.py", "url": "fake://files/missing"}, "Canvas is temporarily unavailable."),
    ({"filename": "fake.pdf", "url": "fake://files/lab3.py"}, "not a PDF"),
])
async def test_unreadable_attachments_go_to_manual_review(sessions, monkeypatch, attachment, error):
    monkeypatch.setattr("app.services.runner.BACKOFF_SECONDS", (0, 0))
    result_id = await add_result(sessions, attachments=[attachment])
    await Runner(sessions, FakeCanvas(), FakeGrader(), 1)._grade(result_id)
    row = await load(sessions, result_id)
    assert (row.status, row.error) == (Status.AI_ERROR_MANUAL_REVIEW, error)


async def test_a_download_is_retried_when_canvas_blips(sessions, monkeypatch):
    monkeypatch.setattr("app.services.runner.BACKOFF_SECONDS", (0, 0))

    class FlakyCanvas(FakeCanvas):
        calls = 0

        async def download(self, url):
            self.calls += 1
            if self.calls < 3:
                raise CanvasError()
            return await super().download(url)

    result_id = await add_result(sessions, attachments=[{"filename": "lab3.py", "url": "fake://files/lab3.py"}])
    await Runner(sessions, FlakyCanvas(), FakeGrader(), 1)._grade(result_id)
    assert (await load(sessions, result_id)).status == Status.AWAITING_REVIEW


async def test_resume_regrades_pending_rows_and_holds_interrupted_publishes(sessions):
    ready = await add_result(sessions, submission_text="answer")
    running = await add_result(sessions, submission_text="answer", status=Status.BEING_GRADED, attempt="2")
    publishing = await add_result(sessions, status=Status.PUBLISHING, attempt="3")
    runner = Runner(sessions, FakeCanvas(), FakeGrader(), 2)
    await runner.resume()
    await asyncio.gather(*runner.tasks)
    assert (await load(sessions, ready)).status == Status.AWAITING_REVIEW
    assert (await load(sessions, running)).status == Status.AWAITING_REVIEW
    held = await load(sessions, publishing)
    assert (held.status, held.error) == (Status.PUBLISH_ERROR_MANUAL_REVIEW, "publish interrupted, check Canvas")


async def test_a_crashed_task_is_logged_and_keeps_its_row(sessions, caplog):
    result_id = await add_result(sessions, submission_text="answer")
    runner = Runner(sessions, FakeCanvas(), ScriptedGrader(RuntimeError("boom")), 1)
    runner.grade(result_id)
    await asyncio.gather(*runner.tasks)
    assert (await load(sessions, result_id)).status == Status.BEING_GRADED
    assert "background task failed" in caplog.messages


async def test_stop_cancels_work_and_leaves_rows_for_resume(sessions):
    result_id = await add_result(sessions, submission_text="answer")
    runner = Runner(sessions, FakeCanvas(), FakeGrader(), 1)
    runner.grade(result_id)
    runner.stop()
    assert all(isinstance(r, asyncio.CancelledError)
               for r in await asyncio.gather(*runner.tasks, return_exceptions=True))
    assert (await load(sessions, result_id)).status == Status.READY_FOR_GRADING


async def test_rows_in_other_states_are_left_alone(sessions):
    result_id = await add_result(sessions, status=Status.APPROVED)
    runner = Runner(sessions, FakeCanvas(), ScriptedGrader(), 1)
    await runner._grade(result_id)
    await runner._publish(result_id)
    assert (await load(sessions, result_id)).status == Status.APPROVED


async def test_a_successful_publish_purges_the_content(sessions):
    result_id = await add_result(sessions, status=Status.PUBLISHING, submission_text="answer", ai_output={},
                                 suggested_feedback="ai", final_score=Decimal(19), final_feedback="Well done")
    canvas = FakeCanvas()
    await Runner(sessions, canvas, FakeGrader(), 1)._publish(result_id)
    row = await load(sessions, result_id)
    assert row.status == Status.PUBLISHED and row.published_at is not None
    assert (row.submission_text, row.ai_output, row.suggested_feedback, row.final_feedback) == (None,) * 4
    assert row.final_score == 19
    assert canvas.published == [{"course_id": "1001", "assignment_id": "2001", "student_id": "3001",
                                  "attempt": "1", "score": Decimal(19), "comment": "Well done"}]
    async with sessions() as session:
        assert (await session.scalars(select(AuditEvent.action))).all() == ["published"]


async def test_three_failed_publishes_end_in_manual_review(sessions, monkeypatch, caplog):
    monkeypatch.setattr("app.domain.publish.BACKOFF_SECONDS", (0, 0))
    result_id = await add_result(sessions, status=Status.PUBLISHING, student_id="3003",
                                 final_score=Decimal(17), final_feedback="Good")
    canvas = FakeCanvas()
    await Runner(sessions, canvas, FakeGrader(), 1)._publish(result_id)
    row = await load(sessions, result_id)
    assert (row.status, row.publish_attempts) == (Status.PUBLISH_ERROR_MANUAL_REVIEW, 3)
    assert row.error == "Canvas publish failed after 3 attempts"
    assert row.final_feedback == "Good"
    assert canvas.published == []
    assert [r.result_id for r in caplog.records if r.message == "publish failed"] == [str(result_id)]
