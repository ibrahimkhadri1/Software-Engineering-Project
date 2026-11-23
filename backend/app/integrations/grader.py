from typing import Protocol

from app.domain.rubric import RubricStruct


class GraderError(Exception):
    pass


class AIGrader(Protocol):
    async def grade(self, rubric: RubricStruct, submission_text: str, correction: str | None) -> object:
        """Returns the model's raw JSON output; ``correction`` names what was wrong with the previous try."""
        ...
