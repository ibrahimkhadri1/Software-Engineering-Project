import re
from dataclasses import dataclass, field
from decimal import Decimal


class RubricError(ValueError):
    pass


@dataclass
class RubricCriterion:
    criterion_id: str
    title: str
    description: str
    max_points: Decimal
    accepted_keywords: list[str] = field(default_factory=list)
    points_per_keyword: Decimal | None = None


@dataclass
class RubricStruct:
    raw_text: str
    criteria: list[RubricCriterion]
    max_score: Decimal


_POINTS = re.compile(r"^\s*(\d+(?:\.\d+)?)(?:\s*(?:pts?|points?))?\b", re.I)
_KEYWORDS = re.compile(r"\[\s*keywords?\s*:\s*([^\];]*?)\s*(?:;\s*(\d+(?:\.\d+)?)\s*each\s*)?\]", re.I)


def rubric_parser(text: str) -> RubricStruct:
    """One criterion per line: ``Title: <points> [keywords: a, b; <n> each] description``.
    An optional ``Total: <points>`` line must match the sum of the criteria."""
    criteria: list[RubricCriterion] = []
    total_line: Decimal | None = None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        title, sep, rest = line.partition(":")
        title = title.strip()
        points_match = _POINTS.match(rest)
        if not sep or not title or not points_match:
            raise RubricError(f"line {number}: expected 'Title: <points>'")
        points = Decimal(points_match.group(1))
        rest = rest[points_match.end():]
        if title.lower() == "total":
            total_line = points
            continue
        if points <= 0:
            raise RubricError(f"line {number}: points must be above 0")
        keywords: list[str] = []
        per_keyword = None
        if keyword_match := _KEYWORDS.search(rest):
            keywords = [k.strip() for k in keyword_match.group(1).split(",") if k.strip()]
            rest = rest[: keyword_match.start()] + rest[keyword_match.end():]
            if keywords and keyword_match.group(2):
                per_keyword = Decimal(keyword_match.group(2))
        description = rest.strip(" \t-–—")
        criteria.append(RubricCriterion(f"c{len(criteria) + 1}", title, description, points, keywords, per_keyword))
    if not criteria:
        raise RubricError("no criteria found")
    max_score = sum((c.max_points for c in criteria), Decimal(0))
    if total_line is not None and total_line != max_score:
        raise RubricError(f"the Total line ({total_line}) does not match the criteria sum ({max_score})")
    return RubricStruct(text, criteria, max_score)
