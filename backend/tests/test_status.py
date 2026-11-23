import pytest

from app.domain.status import TRANSITIONS, Status, TransitionError, transition


def test_happy_path_runs_through_every_core_state():
    s = Status.READY_FOR_GRADING
    for nxt in (Status.BEING_GRADED, Status.AWAITING_REVIEW, Status.APPROVED, Status.PUBLISHING, Status.PUBLISHED):
        s = transition(s, nxt)
    assert s is Status.PUBLISHED


@pytest.mark.parametrize("current,new", [
    (Status.AWAITING_REVIEW, Status.PUBLISHED),
    (Status.REJECTED, Status.APPROVED),
    (Status.AI_ERROR_MANUAL_REVIEW, Status.APPROVED),
    (Status.READY_FOR_GRADING, Status.APPROVED),
    (Status.PUBLISHED, Status.PUBLISHING),
])
def test_shortcuts_to_approval_or_publishing_are_rejected(current, new):
    with pytest.raises(TransitionError):
        transition(current, new)


def test_manual_grade_paths_return_to_review():
    assert transition(Status.REJECTED, Status.AWAITING_REVIEW) is Status.AWAITING_REVIEW
    assert transition(Status.AI_ERROR_MANUAL_REVIEW, Status.AWAITING_REVIEW) is Status.AWAITING_REVIEW


def test_every_status_has_a_transition_entry():
    assert set(TRANSITIONS) == set(Status)
