from collections.abc import Container
from dataclasses import dataclass

from app.domain.status import Status

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)

DedupeKey = tuple[str, str, str, str]


class PublishError(ValueError):
    pass


class DuplicatePublishError(PublishError):
    pass


@dataclass
class PublishAttempt:
    course_id: str
    assignment_id: str
    student_id: str
    submission_id: str  # the Canvas submission attempt number
    previous_attempts: int = 0
    published: bool = False

    @property
    def dedupe_key(self) -> DedupeKey:
        return (self.course_id, self.assignment_id, self.student_id, self.submission_id)

    def check_duplicate_submission(self, published: Container[DedupeKey]) -> bool:
        return self.published or self.dedupe_key in published

    def begin(self, status: Status, published: Container[DedupeKey]) -> None:
        if self.check_duplicate_submission(published):  # first, so a published result reports the duplicate
            raise DuplicatePublishError("this submission was already published")
        if status != Status.APPROVED:
            raise PublishError("only approved results can be published")
        if self.previous_attempts >= MAX_ATTEMPTS:
            raise PublishError("attempt limit reached")

    def successful(self) -> None:
        self.published = True

    def unsuccessful(self) -> float | None:
        """Records a failed try; returns the backoff before the next one, or None when exhausted."""
        self.previous_attempts += 1
        if self.previous_attempts >= MAX_ATTEMPTS:
            return None
        return BACKOFF_SECONDS[self.previous_attempts - 1]
