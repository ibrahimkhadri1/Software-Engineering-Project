from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.rubric import RubricStruct


class ReviewAction(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class ReviewError(ValueError):
    pass


def criteria_total(rubric: RubricStruct, points: dict[str, Decimal]) -> Decimal:
    if set(points) != {c.criterion_id for c in rubric.criteria}:
        raise ReviewError("a score is required for every criterion")
    for c in rubric.criteria:
        if not 0 <= points[c.criterion_id] <= c.max_points:
            raise ReviewError(f"{c.title} must be between 0 and {c.max_points}")
    return sum(points.values(), Decimal(0))


@dataclass
class PredictionAcceptStatus:
    """The reviewer's decision on one AI suggestion; ``actual_*`` is the untouched suggestion."""

    max_score: Decimal
    actual_score: Decimal | None = None
    actual_feedback: str | None = None
    final_score: Decimal | None = None
    final_feedback: str | None = None
    comments: str = ""
    validation_status: ReviewAction = ReviewAction.PENDING

    @property
    def review_complete(self) -> bool:
        return self.final_score is not None

    def accept_prediction(self) -> None:
        self._require_prediction()
        self._set_final(self.actual_score, self.actual_feedback, ReviewAction.ACCEPTED)

    def edit_prediction(self, score: Decimal, feedback: str | None) -> None:
        self._require_prediction()
        self._set_final(score, feedback, ReviewAction.EDITED)

    def reject_prediction(self, comments: str = "") -> None:
        self._require_prediction()
        self.final_score = self.final_feedback = None
        self.comments = comments
        self.validation_status = ReviewAction.REJECTED

    def undo_reject(self) -> None:
        if self.validation_status != ReviewAction.REJECTED:
            raise ReviewError("only a rejected suggestion can be restored")
        self.final_score = self.final_feedback = None
        self.comments = ""
        self.validation_status = ReviewAction.PENDING

    def manual_grade(self, score: Decimal, feedback: str | None) -> None:
        if self.validation_status != ReviewAction.REJECTED and self.actual_score is not None:
            raise ReviewError("reject the suggestion before grading manually")
        self._set_final(score, feedback, self.validation_status)

    def _require_prediction(self) -> None:
        if self.actual_score is None:
            raise ReviewError("no AI suggestion to review")

    def _set_final(self, score: Decimal, feedback: str | None, action: ReviewAction) -> None:
        if not 0 <= score <= self.max_score:
            raise ReviewError("score must be between 0 and the rubric maximum")
        self.final_score, self.final_feedback, self.validation_status = score, (feedback or "").strip(), action
