"""TC-005 PredictionAcceptStatus."""
from decimal import Decimal

import pytest

from app.domain.review import PredictionAcceptStatus, ReviewAction, ReviewError, criteria_total


@pytest.fixture
def review():
    return PredictionAcceptStatus(Decimal(21), Decimal("17.5"), "Solid work.")


def test_accept_copies_the_suggestion(review):
    review.accept_prediction()
    assert review.validation_status is ReviewAction.ACCEPTED
    assert (review.final_score, review.final_feedback) == (Decimal("17.5"), "Solid work.")
    assert review.review_complete


def test_edit_keeps_the_original(review):
    review.edit_prediction(Decimal(20), "Better than the model thought.")
    assert review.validation_status is ReviewAction.EDITED
    assert review.final_score == Decimal(20)
    assert review.actual_score == Decimal("17.5")
    assert review.review_complete


def test_reject_keeps_the_saved_grade_until_a_manual_one(review):
    review.edit_prediction(Decimal(20), "Edited.")
    review.reject_prediction("Plagiarism suspected")
    assert review.validation_status is ReviewAction.REJECTED
    assert (review.final_score, review.final_feedback) == (Decimal(20), "Edited.")
    assert review.comments == "Plagiarism suspected"
    review.manual_grade(Decimal(0), "See me.")
    assert review.final_score == 0 and review.validation_status is ReviewAction.REJECTED


def test_manual_grade_needs_a_reject_first_when_there_is_a_suggestion(review):
    with pytest.raises(ReviewError):
        review.manual_grade(Decimal(1), "x")


def test_manual_grade_works_when_the_ai_failed():
    review = PredictionAcceptStatus(Decimal(21))
    with pytest.raises(ReviewError):
        review.accept_prediction()
    review.manual_grade(Decimal(12), "Graded by hand.")
    assert review.review_complete and review.validation_status is ReviewAction.PENDING


@pytest.mark.parametrize("score", [Decimal(-1), Decimal("21.5")])
def test_out_of_range_score_is_rejected(review, score):
    with pytest.raises(ReviewError):
        review.edit_prediction(score, "ok")
    assert review.validation_status is ReviewAction.PENDING and not review.review_complete


@pytest.mark.parametrize("feedback", [None, "", "   "])
def test_a_grader_may_leave_the_feedback_empty(review, feedback):
    review.edit_prediction(Decimal(5), feedback)
    assert (review.final_score, review.final_feedback) == (Decimal(5), "")


def test_undo_reject_restores_the_unreviewed_suggestion(review):
    with pytest.raises(ReviewError):
        review.undo_reject()
    review.reject_prediction("wrong student")
    review.undo_reject()
    assert (review.validation_status, review.final_score, review.comments) == (ReviewAction.PENDING, None, "")
    review.accept_prediction()
    assert review.final_score == Decimal("17.5")


def test_undo_reject_restores_the_saved_grade(review):
    """Beta bug 005."""
    review.edit_prediction(Decimal(20), "Edited.")
    review.reject_prediction("wrong student")
    review.undo_reject()
    assert (review.validation_status, review.final_score, review.final_feedback) == (
        ReviewAction.EDITED, Decimal(20), "Edited.")


def test_criterion_scores_add_up_to_the_final_score(rubric):
    assert criteria_total(rubric, {"c1": Decimal(8), "c2": Decimal("4.5"), "c3": Decimal(0)}) == Decimal("12.5")


@pytest.mark.parametrize("points", [
    {"c1": 8, "c2": 4},
    {"c1": 8, "c2": 4, "c3": 2, "c4": 1},
    {"c1": 11, "c2": 4, "c3": 2},
    {"c1": 8, "c2": -1, "c3": 2},
])
def test_criterion_scores_must_cover_the_rubric_and_stay_in_range(rubric, points):
    with pytest.raises(ReviewError):
        criteria_total(rubric, {k: Decimal(v) for k, v in points.items()})
