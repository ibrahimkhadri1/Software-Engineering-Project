"""TC-005 PredictionAcceptStatus."""
from decimal import Decimal

import pytest

from app.domain.review import PredictionAcceptStatus, ReviewAction, ReviewError


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


def test_reject_clears_the_final_grade_until_a_manual_one(review):
    review.accept_prediction()
    review.reject_prediction("Plagiarism suspected")
    assert review.validation_status is ReviewAction.REJECTED
    assert review.final_score is None and not review.review_complete
    assert review.comments == "Plagiarism suspected"
    review.manual_grade(Decimal(0), "See me.")
    assert review.review_complete and review.validation_status is ReviewAction.REJECTED


def test_manual_grade_needs_a_reject_first_when_there_is_a_suggestion(review):
    with pytest.raises(ReviewError):
        review.manual_grade(Decimal(1), "x")


def test_manual_grade_works_when_the_ai_failed():
    review = PredictionAcceptStatus(Decimal(21))
    with pytest.raises(ReviewError):
        review.accept_prediction()
    review.manual_grade(Decimal(12), "Graded by hand.")
    assert review.review_complete and review.validation_status is ReviewAction.PENDING


@pytest.mark.parametrize("score,feedback", [
    (Decimal(-1), "ok"),
    (Decimal("21.5"), "ok"),
    (Decimal(5), ""),
    (Decimal(5), "   "),
])
def test_out_of_range_score_or_empty_feedback_is_rejected(review, score, feedback):
    with pytest.raises(ReviewError):
        review.edit_prediction(score, feedback)
    assert review.validation_status is ReviewAction.PENDING and not review.review_complete
