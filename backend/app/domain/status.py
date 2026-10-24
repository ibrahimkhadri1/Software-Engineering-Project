from enum import StrEnum


class Status(StrEnum):
    READY_FOR_GRADING = "READY_FOR_GRADING"
    BEING_GRADED = "BEING_GRADED"
    AI_ERROR_MANUAL_REVIEW = "AI_ERROR_MANUAL_REVIEW"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    PUBLISHING = "PUBLISHING"
    PUBLISH_ERROR_MANUAL_REVIEW = "PUBLISH_ERROR_MANUAL_REVIEW"
    PUBLISHED = "PUBLISHED"


# A manual grade (after Reject or an AI failure) re-enters review; nothing jumps straight to APPROVED.
TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.READY_FOR_GRADING: frozenset({Status.BEING_GRADED}),
    Status.BEING_GRADED: frozenset({Status.AWAITING_REVIEW, Status.AI_ERROR_MANUAL_REVIEW}),
    Status.AI_ERROR_MANUAL_REVIEW: frozenset({Status.AWAITING_REVIEW}),
    Status.AWAITING_REVIEW: frozenset({Status.APPROVED, Status.REJECTED}),
    Status.REJECTED: frozenset({Status.AWAITING_REVIEW}),
    Status.APPROVED: frozenset({Status.PUBLISHING}),
    Status.PUBLISHING: frozenset({Status.PUBLISHED, Status.PUBLISH_ERROR_MANUAL_REVIEW}),
    Status.PUBLISH_ERROR_MANUAL_REVIEW: frozenset(),
    Status.PUBLISHED: frozenset(),
}


class TransitionError(ValueError):
    pass


def transition(current: Status, new: Status) -> Status:
    if new not in TRANSITIONS[current]:
        raise TransitionError(f"{current} -> {new}")
    return new
