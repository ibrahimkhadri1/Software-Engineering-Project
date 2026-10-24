from decimal import Decimal
from pathlib import Path

from app.domain.partial_credit import PartialCreditCounter
from app.domain.rubric import RubricStruct
from app.integrations.canvas import Assignment, Attachment, CanvasError, Course, Submission

INVALID_MARKER = "[fake:invalid]"
OUT_OF_RANGE_MARKER = "[fake:out-of-range]"

COURSE = Course("1001", "CMPE 131 Sandbox (fake)")
LAB = Assignment("2001", "Lab 3: Recursion", Decimal(21), ["online_upload", "online_text_entry"])
ON_PAPER = Assignment("2002", "Midterm (on paper)", Decimal(50), ["on_paper"])

FILES = {
    "fake://files/lab3.py": b"def factorial(n):\n    # base case\n    if n == 0:\n        return 1\n"
                            b"    return n * factorial(n - 1)  # recursion\n",
    "fake://files/Lab3.java": b"class Lab3 {\n  static int factorial(int n) {\n    int result = 1;\n"
                              b"    for (int i = 2; i <= n; i++) result *= i;  // loop\n    return result;\n  }\n}\n",
    "fake://files/notes.txt": f"{OUT_OF_RANGE_MARKER} Recursion with a base case.".encode(),
    "fake://files/essay.pdf": (Path(__file__).parent / "fixtures" / "essay.pdf").read_bytes(),
}

SUBMISSIONS = [
    Submission("3001", "Ada Lovelace", "1", body="Factorial uses recursion and stops at the base case n == 0."),
    Submission("3002", "Alan Turing", "1", attachments=[Attachment("lab3.py", "fake://files/lab3.py")]),
    Submission("3003", "Grace Hopper", "2", attachments=[Attachment("Lab3.java", "fake://files/Lab3.java")]),
    Submission("3004", "Edsger Dijkstra", "1", attachments=[Attachment("essay.pdf", "fake://files/essay.pdf")]),
    Submission("3005", "Barbara Liskov", "1", attachments=[Attachment("screenshot.jpeg", "fake://files/x.jpeg")]),
    Submission("3006", "Donald Knuth", "1", body=f"{INVALID_MARKER} An answer the fake grader cannot score."),
    Submission("3007", "Margaret Hamilton", "1", attachments=[Attachment("notes.txt", "fake://files/notes.txt")]),
]
PUBLISH_FAILS_FOR = frozenset({"3003"})


class FakeCanvas:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def courses(self) -> list[Course]:
        return [COURSE]

    async def assignments(self, course_id: str) -> list[Assignment]:
        return [LAB, ON_PAPER] if course_id == COURSE.id else []

    async def submissions(self, course_id: str, assignment_id: str) -> list[Submission]:
        return list(SUBMISSIONS) if (course_id, assignment_id) == (COURSE.id, LAB.id) else []

    async def download(self, url: str) -> bytes:
        if url not in FILES:
            raise CanvasError()
        return FILES[url]

    async def publish(self, course_id: str, assignment_id: str, student_id: str, attempt: str,
                      score: Decimal, comment: str) -> None:
        if student_id in PUBLISH_FAILS_FOR:
            raise CanvasError()
        self.published.append({"course_id": course_id, "assignment_id": assignment_id, "student_id": student_id,
                               "attempt": attempt, "score": score, "comment": comment})


class FakeGrader:
    async def grade(self, rubric: RubricStruct, submission_text: str, correction: str | None) -> object:
        if INVALID_MARKER in submission_text:
            return {"schema_version": "1.0", "criteria": "not a list"}
        criteria = []
        for c in rubric.criteria:
            points = PartialCreditCounter(c).add_partialcredit(submission_text) if c.accepted_keywords else c.max_points
            if OUT_OF_RANGE_MARKER in submission_text:
                points = c.max_points + 1
            criteria.append({"criterion_id": c.criterion_id, "awarded_points": float(points),
                             "rationale": f"Fake grader: {c.title} scored without a model.",
                             "feedback": f"{c.title}: compare your work with the rubric."})
        return {"schema_version": "1.0", "criteria": criteria, "overall_feedback": "Fake grader feedback.",
                "manual_review_required": False, "warnings": []}
