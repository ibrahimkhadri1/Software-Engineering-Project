import re
from decimal import Decimal

from app.domain.rubric import RubricCriterion


class PartialCreditCounter:
    def __init__(self, criterion: RubricCriterion) -> None:
        self.accepted_keywords = criterion.accepted_keywords
        self.points_per_keyword = criterion.points_per_keyword
        self.max_partialcredit = criterion.max_points
        self.matched: set[str] = set()
        self.count_partialcredit = Decimal(0)

    def add_partialcredit(self, text: str) -> Decimal:
        for keyword in self.accepted_keywords:
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE):
                self.matched.add(keyword.lower())
        if self.points_per_keyword is None:  # multiply first so all keywords give exactly the max
            credit = self.max_partialcredit * len(self.matched) / max(len(self.accepted_keywords), 1)
        else:
            credit = len(self.matched) * self.points_per_keyword
        self.count_partialcredit = min(credit, self.max_partialcredit)
        return self.count_partialcredit

    def validate_partialcredit(self) -> bool:
        return 0 <= self.count_partialcredit <= self.max_partialcredit
