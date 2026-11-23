"""TC-004 PartialCreditCounter."""
from decimal import Decimal

from app.domain.partial_credit import PartialCreditCounter
from app.domain.rubric import rubric_parser


def test_matched_keywords_earn_the_defined_credit(rubric):
    counter = PartialCreditCounter(rubric.criteria[2])
    assert counter.add_partialcredit("I used a LOOP and a base case here.") == Decimal(4)
    assert counter.validate_partialcredit()


def test_missing_keywords_earn_nothing(rubric):
    counter = PartialCreditCounter(rubric.criteria[2])
    assert counter.add_partialcredit("looping recursively") == Decimal(0)
    assert counter.validate_partialcredit()


def test_credit_is_capped_and_keywords_count_once_across_files(rubric):
    criterion = rubric.criteria[2]
    criterion.points_per_keyword = Decimal(5)
    counter = PartialCreditCounter(criterion)
    counter.add_partialcredit("loop loop loop")
    counter.add_partialcredit("recursion with a base case")
    assert counter.count_partialcredit == criterion.max_points == Decimal(6)
    assert counter.validate_partialcredit()


def test_even_share_reaches_exactly_the_max():
    counter = PartialCreditCounter(rubric_parser("Terms: 10 [keywords: a, b, c]").criteria[0])
    assert counter.add_partialcredit("a") == Decimal(10) / 3
    assert counter.add_partialcredit("b c") == Decimal(10)


def test_criterion_without_keywords_gives_no_credit(rubric):
    counter = PartialCreditCounter(rubric.criteria[0])
    assert counter.add_partialcredit("anything") == Decimal(0)
