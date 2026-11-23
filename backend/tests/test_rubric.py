"""TC-001 RubricStruct."""
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from app.domain.pdf import PdfError, pdf_text
from app.domain.rubric import RubricError, rubric_parser
from tests.conftest import RUBRIC_TEXT, make_pdf


def encrypted(pdf: bytes) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))
    writer.encrypt("pw")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_valid_rubric_becomes_criteria_with_correct_max(rubric):
    assert [c.criterion_id for c in rubric.criteria] == ["c1", "c2", "c3"]
    assert rubric.max_score == Decimal(21)
    assert rubric.criteria[0].title == "Correctness"
    assert rubric.criteria[0].description == "Program produces the right output"
    assert rubric.criteria[0].max_points == Decimal(10)
    assert rubric.criteria[1].description == ""
    assert rubric.criteria[2].accepted_keywords == ["loop", "recursion", "base case"]
    assert rubric.criteria[2].points_per_keyword == Decimal(2)
    assert rubric.criteria[2].description == "names the key ideas"
    assert rubric.raw_text == RUBRIC_TEXT


def test_tabs_from_pasted_tables_are_trimmed():
    assert rubric_parser("Correctness:\t10\tProgram runs").criteria[0].description == "Program runs"


def test_keywords_without_each_have_no_fixed_rate():
    r = rubric_parser("Terms: 6 [keywords: a, b, c]")
    assert r.criteria[0].accepted_keywords == ["a", "b", "c"]
    assert r.criteria[0].points_per_keyword is None


@pytest.mark.parametrize("text", [
    "",
    "   \n\n",
    "Correctness",
    "Correctness: ten",
    ": 10",
    "Correctness: 0",
    "Correctness: 10\nTotal: 11",
])
def test_missing_or_invalid_rubric_raises(text):
    with pytest.raises(RubricError):
        rubric_parser(text)


def test_pdf_rubric_text_is_parsed():
    text = pdf_text(make_pdf(["Correctness: 10 points", "Style: 5"]))
    assert rubric_parser(text).max_score == Decimal(15)


def test_pdf_without_text_or_not_a_pdf_raises():
    with pytest.raises(PdfError):
        pdf_text(b"GIF89a not a pdf")
    with pytest.raises(PdfError, match="encrypted"):
        pdf_text(encrypted(make_pdf(["secret"])))
    with pytest.raises(PdfError):
        pdf_text(make_pdf([]))
    with pytest.raises(PdfError):
        pdf_text(b"%PDF-1.4 garbage")
    with pytest.raises(PdfError):
        pdf_text(make_pdf(["x"]), max_pages=0)


def test_any_parser_crash_becomes_a_pdf_error(monkeypatch):
    def broken(*_):
        raise TypeError("malformed object")

    monkeypatch.setattr("app.domain.pdf.PdfReader", broken)
    with pytest.raises(PdfError, match="unreadable"):
        pdf_text(make_pdf(["x"]))
