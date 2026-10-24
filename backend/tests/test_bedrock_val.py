"""TC-003 BedrockVal (and the TC-008 attempt limit)."""
import copy
from decimal import Decimal

import pytest

from app.domain.bedrock_val import BedrockVal, BedrockValError

VALID = {
    "schema_version": "1.0",
    "criteria": [
        {"criterion_id": "c1", "awarded_points": 8.5, "rationale": "3 of 4 cases right.", "feedback": "Fix the edge."},
        {"criterion_id": "c2", "awarded_points": 5, "rationale": "Clean.", "feedback": "Good style."},
        {"criterion_id": "c3", "awarded_points": 4, "rationale": "Two concepts named.", "feedback": "Name base cases."},
    ],
    "overall_feedback": "Solid work.",
    "manual_review_required": False,
    "warnings": [],
}


def with_(path: list, value):
    raw = copy.deepcopy(VALID)
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return raw


def test_valid_output_is_accepted_and_total_recomputed(rubric):
    val = BedrockVal(rubric)
    grade = val.validate_output(VALID)
    assert val.valid_output and val.retry_attempt == 1
    assert grade.total == Decimal("17.5")
    assert grade.criteria[0].awarded_points == Decimal("8.5")
    assert val.max_score == Decimal(21) and val.min_score == 0


@pytest.mark.parametrize("raw", [
    "not json",
    with_(["schema_version"], "2.0"),
    with_(["criteria"], "c1"),
    with_(["criteria"], VALID["criteria"][:2]),
    with_(["criteria"], VALID["criteria"] + [{**VALID["criteria"][0], "criterion_id": "c9"}]),
    with_(["criteria"], VALID["criteria"] + [VALID["criteria"][0]]),
    with_(["criteria"], ["c1"]),
    with_(["criteria", 0, "criterion_id"], ["c1"]),
    with_(["criteria", 0, "awarded_points"], -1),
    with_(["criteria", 0, "awarded_points"], 10.5),
    with_(["criteria", 0, "awarded_points"], float("nan")),
    with_(["criteria", 0, "awarded_points"], float("inf")),
    with_(["criteria", 0, "awarded_points"], "8"),
    with_(["criteria", 0, "awarded_points"], True),
    with_(["criteria", 0, "rationale"], ""),
    with_(["criteria", 0, "feedback"], None),
    with_(["overall_feedback"], " "),
    with_(["warnings"], "none"),
    with_(["manual_review_required"], "no"),
])
def test_invalid_output_is_rejected(rubric, raw):
    val = BedrockVal(rubric)
    with pytest.raises(BedrockValError):
        val.validate_output(raw)
    assert not val.valid_output


def test_attempts_never_exceed_three(rubric):
    val = BedrockVal(rubric)
    for _ in range(3):
        with pytest.raises(BedrockValError):
            val.validate_output({})
    assert val.retry_attempt == 3 and not val.can_retry
    with pytest.raises(BedrockValError, match="attempt limit"):
        val.validate_output(VALID)
    assert val.retry_attempt == 3
