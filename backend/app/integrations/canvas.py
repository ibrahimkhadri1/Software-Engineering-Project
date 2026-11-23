from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from app.core.errors import AppError

GRADABLE_SUBMISSION_TYPES = frozenset({"online_text_entry", "online_upload"})


class CanvasError(AppError):
    def __init__(self) -> None:
        super().__init__("CANVAS_UNAVAILABLE", "Canvas is temporarily unavailable.", 503, retryable=True)


@dataclass
class Course:
    id: str
    name: str


@dataclass
class Assignment:
    id: str
    name: str
    points_possible: Decimal
    submission_types: list[str]

    @property
    def supported(self) -> bool:
        return not GRADABLE_SUBMISSION_TYPES.isdisjoint(self.submission_types)


@dataclass
class Attachment:
    filename: str
    url: str


@dataclass
class Submission:
    student_id: str
    student_name: str
    attempt: str
    body: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


class Canvas(Protocol):
    async def courses(self) -> list[Course]: ...

    async def assignments(self, course_id: str) -> list[Assignment]: ...

    async def submissions(self, course_id: str, assignment_id: str) -> list[Submission]: ...

    async def download(self, url: str) -> bytes: ...

    async def publish(self, course_id: str, assignment_id: str, student_id: str, attempt: str,
                      score: Decimal, comment: str) -> None: ...
