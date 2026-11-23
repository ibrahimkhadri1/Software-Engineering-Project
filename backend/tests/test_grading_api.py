import time
import uuid

import pytest
from conftest import RUBRIC_TEXT

from app.integrations.canvas import CanvasError, Submission

BUSY = {"READY_FOR_GRADING", "BEING_GRADED", "PUBLISHING"}


def wait_idle(api, batch_id) -> dict:
    for _ in range(200):
        batch = api.get(f"/api/grading/batches/{batch_id}").json()
        if not any(r["status"] in BUSY for r in batch["results"]):
            return batch
        time.sleep(0.02)
    raise AssertionError("batch still busy")


def start_batch(api) -> dict:
    body = {"course_id": "1001", "assignment_id": "2001", "rubric_text": RUBRIC_TEXT}
    r = api.post("/api/grading/batches", json=body)
    assert r.status_code == 202
    return wait_idle(api, r.json()["batch_id"])


def result_id(batch, name) -> str:
    return next(r["id"] for r in batch["results"] if r["student_name"] == name)


def review(api, rid, **body):
    return api.patch(f"/api/grading/results/{rid}/review", json=body)


def publish(api, batch, *ids) -> list[dict]:
    r = api.post(f"/api/grading/batches/{batch['id']}/approve-and-publish", json={"result_ids": list(ids)})
    return r.json()["outcomes"]


def status(api, rid) -> str:
    return api.get(f"/api/grading/results/{rid}").json()["status"]


def test_courses_and_assignments_come_from_canvas(api):
    assert api.get("/api/canvas/courses").json() == [{"id": "1001", "name": "CMPE 131 Sandbox (fake)"}]
    assignments = api.get("/api/canvas/courses/1001/assignments").json()
    assert [(a["id"], a["supported"]) for a in assignments] == [("2001", True), ("2002", False)]


def test_a_batch_grades_every_supported_submission(api, caplog):
    batch = start_batch(api)
    rejected = [r.result_id for r in caplog.records if r.message == "submission not accepted"]
    assert rejected == [result_id(batch, "Barbara Liskov")]
    assert batch["counts"] == {"total": 7, "pending_ai": 0, "ready_for_review": 4, "approved": 0, "failed": 3}
    assert batch["max_score"] == 21
    scores = {r["student_name"]: (r["suggested_score"], r["error"]) for r in batch["results"]}
    assert scores == {
        "Ada Lovelace": (19, None), "Alan Turing": (19, None), "Grace Hopper": (17, None),
        "Edsger Dijkstra": (21, None), "Barbara Liskov": (None, "unsupported file type"),
        "Donald Knuth": (None, "AI output invalid after 3 attempts"),
        "Margaret Hamilton": (None, "AI output invalid after 3 attempts"),
    }
    detail = api.get(f"/api/grading/results/{result_id(batch, 'Ada Lovelace')}").json()
    assert detail["submission_text"].startswith("Factorial uses recursion")
    assert [c["title"] for c in detail["criteria"]] == ["Correctness", "Style", "Concepts"]
    assert len(detail["ai_output"]["criteria"]) == 3


@pytest.mark.parametrize("change, status_code, code", [
    ({"assignment_id": "9999"}, 404, "NOT_FOUND"),
    ({"assignment_id": "2002"}, 422, "ASSIGNMENT_UNSUPPORTED"),
    ({"rubric_text": "no points here"}, 422, "RUBRIC_INVALID"),
    ({"rubric_text": "Correctness: 20"}, 422, "RUBRIC_POINTS_MISMATCH"),
])
def test_batch_creation_refuses_bad_input(api, change, status_code, code):
    body = {"course_id": "1001", "assignment_id": "2001", "rubric_text": RUBRIC_TEXT} | change
    r = api.post("/api/grading/batches", json=body)
    assert (r.status_code, r.json()["error"]["code"]) == (status_code, code)


def test_accepted_result_publishes_once(api):
    """TC-005 accept, TC-006 a second publish posts nothing."""
    batch = start_batch(api)
    ada = result_id(batch, "Ada Lovelace")
    assert review(api, ada, action="accept").json()["final_score"] == 19
    assert publish(api, batch, ada) == [{"result_id": ada, "ok": True}]
    wait_idle(api, batch["id"])
    detail = api.get(f"/api/grading/results/{ada}").json()
    assert (detail["status"], detail["submission_text"], detail["final_feedback"]) == ("PUBLISHED", None, None)
    assert len(api.app.state.canvas.published) == 1
    assert publish(api, batch, ada)[0]["code"] == "DUPLICATE_PUBLISH"
    assert review(api, ada, action="accept").json()["error"]["code"] == "INVALID_STATE"
    assert len(api.app.state.canvas.published) == 1


def test_the_same_submission_in_a_second_batch_is_not_published_again(api):
    first, second = start_batch(api), start_batch(api)
    for batch in (first, second):
        review(api, result_id(batch, "Ada Lovelace"), action="accept")
    publish(api, first, result_id(first, "Ada Lovelace"))
    wait_idle(api, first["id"])
    assert publish(api, second, result_id(second, "Ada Lovelace"))[0]["code"] == "DUPLICATE_PUBLISH"
    assert status(api, result_id(second, "Ada Lovelace")) == "AWAITING_REVIEW"


def test_only_reviewed_results_of_the_batch_are_published(api):
    batch = start_batch(api)
    alan = result_id(batch, "Alan Turing")
    unknown = str(uuid.uuid4())
    outcomes = publish(api, batch, alan, unknown)
    assert [o["code"] for o in outcomes] == ["NOT_REVIEWED", "NOT_FOUND"]
    assert status(api, alan) == "AWAITING_REVIEW"
    assert api.app.state.canvas.published == []


def test_rejected_result_can_be_graded_manually_and_published(api):
    """D7: Reject, then a manual grade that is approved and published like any other."""
    batch = start_batch(api)
    alan = result_id(batch, "Alan Turing")
    assert review(api, alan, action="reject", comments="misses the point").json()["status"] == "REJECTED"
    assert publish(api, batch, alan)[0]["code"] == "NOT_REVIEWED"
    graded = review(api, alan, action="manual", score=15, feedback="Graded by hand").json()
    assert (graded["status"], graded["review_action"], graded["final_score"]) == ("AWAITING_REVIEW", "rejected", 15)
    assert publish(api, batch, alan)[0]["ok"]
    wait_idle(api, batch["id"])
    assert api.app.state.canvas.published[0]["score"] == 15


def test_failed_ai_results_need_a_manual_grade(api):
    batch = start_batch(api)
    barbara, donald = result_id(batch, "Barbara Liskov"), result_id(batch, "Donald Knuth")
    assert review(api, donald, action="accept").json()["error"]["code"] == "REVIEW_INVALID"
    assert review(api, barbara, action="manual", score=10, feedback="Image checked by hand").json()["status"] == \
        "AWAITING_REVIEW"


@pytest.mark.parametrize("body, code", [
    ({"action": "edit", "score": 22, "feedback": "x"}, "REVIEW_INVALID"),
    ({"action": "edit", "feedback": "x"}, "REVIEW_INVALID"),
    ({"action": "edit", "score": 5, "feedback": " "}, "REVIEW_INVALID"),
    ({"action": "manual", "score": 5, "feedback": "x"}, "REVIEW_INVALID"),
    ({"action": "edit", "score": "NaN", "feedback": "x"}, "VALIDATION_ERROR"),
    ({"action": "approve"}, "VALIDATION_ERROR"),
])
def test_review_input_is_validated(api, body, code):
    batch = start_batch(api)
    r = review(api, result_id(batch, "Alan Turing"), **body)
    assert (r.status_code, r.json()["error"]["code"]) == (422, code)


def test_edit_keeps_the_ai_suggestion(api):
    batch = start_batch(api)
    edited = review(api, result_id(batch, "Alan Turing"), action="edit", score=18.5, feedback="Nearly there").json()
    assert (edited["suggested_score"], edited["final_score"], edited["review_action"]) == (19, 18.5, "edited")


def test_canvas_failure_publish_ends_in_manual_review(api, monkeypatch):
    """TC-009 through the API: the fake Canvas always fails for Grace Hopper."""
    monkeypatch.setattr("app.domain.publish.BACKOFF_SECONDS", (0, 0))
    batch = start_batch(api)
    grace = result_id(batch, "Grace Hopper")
    review(api, grace, action="accept")
    assert publish(api, batch, grace)[0]["ok"]
    batch = wait_idle(api, batch["id"])
    assert status(api, grace) == "PUBLISH_ERROR_MANUAL_REVIEW"
    assert batch["counts"]["failed"] == 4


def test_canvas_outage_has_a_clear_message(api, monkeypatch):
    async def down():
        raise CanvasError()

    monkeypatch.setattr(api.app.state.canvas, "courses", down)
    r = api.get("/api/canvas/courses")
    assert r.status_code == 503
    assert r.json()["error"]["message"] == "Canvas is temporarily unavailable."


@pytest.mark.parametrize("path", ["/api/grading/batches/{}", "/api/grading/results/{}"])
def test_unknown_ids_are_not_found(api, path):
    assert api.get(path.format(uuid.uuid4())).status_code == 404


def test_online_text_gets_the_file_size_limit(api, monkeypatch):
    monkeypatch.setattr("app.integrations.fakes.SUBMISSIONS", [Submission("3001", "Ada", "1", body="x" * 5_000_001)])
    batch = start_batch(api)
    assert [(r["status"], r["error"]) for r in batch["results"]] == [("AI_ERROR_MANUAL_REVIEW", "file too large")]
