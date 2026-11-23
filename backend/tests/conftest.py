import pytest

from app.domain.rubric import rubric_parser

RUBRIC_TEXT = """
Correctness: 10 points - Program produces the right output
Style: 5 pts
Concepts: 6 [keywords: loop, recursion, base case; 2 each] names the key ideas
Total: 21
"""


@pytest.fixture
def rubric():
    return rubric_parser(RUBRIC_TEXT)


def make_pdf(lines: list[str]) -> bytes:
    text = " ".join("(" + line.replace("(", r"\(").replace(")", r"\)") + ") Tj T*" for line in lines)
    content = f"BT /F1 12 Tf 14 TL 72 720 Td {text} ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        " /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")
