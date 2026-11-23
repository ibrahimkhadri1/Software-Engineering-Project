from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.rubric import RubricStruct

MAX_ATTEMPTS = 3
SCHEMA_VERSION = "1.0"


class BedrockValError(ValueError):
    pass


@dataclass
class CriterionScore:
    criterion_id: str
    awarded_points: Decimal
    rationale: str
    feedback: str


@dataclass
class GradeSuggestion:
    criteria: list[CriterionScore]
    total: Decimal
    overall_feedback: str
    manual_review_required: bool = False
    warnings: list[str] = field(default_factory=list)


class BedrockVal:
    def __init__(self, rubric: RubricStruct) -> None:
        self.rubric = rubric
        self.min_score = Decimal(0)
        self.max_score = rubric.max_score
        self.retry_attempt = 0
        self.valid_output = False

    @property
    def can_retry(self) -> bool:
        return self.retry_attempt < MAX_ATTEMPTS

    def validate_output(self, raw: object) -> GradeSuggestion:
        if not self.can_retry:
            raise BedrockValError("attempt limit reached")
        self.retry_attempt += 1
        self.valid_output = False
        grade = _parse(raw, self.rubric)
        self.valid_output = True
        return grade


def _text(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BedrockValError(f"missing {key}")
    return value.strip()


def _points(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BedrockValError("score is not a number")
    points = Decimal(str(value))
    if not points.is_finite():
        raise BedrockValError("score is not finite")
    return round(points, 2)


def _parse(raw: object, rubric: RubricStruct) -> GradeSuggestion:
    if not isinstance(raw, dict):
        raise BedrockValError("response is not an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise BedrockValError("unexpected schema version")
    items = raw.get("criteria")
    if not isinstance(items, list):
        raise BedrockValError("criteria missing")
    by_id = {c.criterion_id: c for c in rubric.criteria}
    scores: dict[str, CriterionScore] = {}
    for item in items:
        if not isinstance(item, dict):
            raise BedrockValError("criterion is not an object")
        cid = item.get("criterion_id")
        if not isinstance(cid, str) or cid not in by_id:
            raise BedrockValError("unknown criterion")
        if cid in scores:
            raise BedrockValError("criterion repeated")
        points = _points(item.get("awarded_points"))
        if not 0 <= points <= by_id[cid].max_points:
            raise BedrockValError("score out of range")
        scores[cid] = CriterionScore(cid, points, _text(item, "rationale"), _text(item, "feedback"))
    if scores.keys() != by_id.keys():
        raise BedrockValError("criterion missing")
    ordered = [scores[cid] for cid in by_id]
    total = sum((s.awarded_points for s in ordered), Decimal(0))
    warnings = raw.get("warnings", [])
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise BedrockValError("warnings malformed")
    manual_review = raw.get("manual_review_required", False)
    if not isinstance(manual_review, bool):
        raise BedrockValError("manual_review_required malformed")
    return GradeSuggestion(ordered, total, _text(raw, "overall_feedback"), manual_review, warnings)
