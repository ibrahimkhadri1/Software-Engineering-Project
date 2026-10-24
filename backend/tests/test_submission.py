"""TC-002 SubmissionStatus."""
import pytest

from app.domain.submission import SubmissionError, SubmissionStatus, extract_text
from tests.conftest import make_pdf


@pytest.mark.parametrize("name", ["a.pdf", "a.py", "a.java", "a.txt", "A.PY", "dir/x.TXT"])
def test_supported_types_are_accepted(name):
    assert SubmissionStatus.check_filetype(name)
    assert SubmissionStatus.for_submission([name]).is_accepted


@pytest.mark.parametrize("name", ["a.jpeg", "a.jpg", "a.zip", "a.docx", "noext", "a.py.exe"])
def test_unsupported_types_are_rejected(name):
    assert not SubmissionStatus.check_filetype(name)
    status = SubmissionStatus.for_submission(["ok.py", name])
    assert status.is_rejected and status.error == "unsupported file type"


def test_file_without_extension_is_named_in_file_type():
    assert SubmissionStatus.for_submission(["ok.py", "noext"]).file_type == ".py, no extension"


def test_online_text_and_empty_submission():
    assert SubmissionStatus.for_submission([], "my answer").file_type == "online_text"
    empty = SubmissionStatus.for_submission([], "  \n")
    assert empty.is_rejected and empty.error == "empty submission"


def test_text_files_are_read_as_text():
    assert extract_text("a.py", b"import os\nos.system('rm -rf /')\n").startswith("import os")
    assert "�" in extract_text("a.txt", b"\xc3 bad utf8")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be"])
def test_common_text_encodings_decode_cleanly(encoding):
    data = "print('héllo')\n".encode(encoding)
    if encoding == "utf-16-be":
        data = b"\xfe\xff" + data
    assert extract_text("out.txt", data) == "print('héllo')\n"


def test_nul_characters_are_dropped():
    assert extract_text("a.py", b"x = 1\x00\n") == "x = 1\n"


def test_pdf_submission_text_is_extracted():
    assert "hello" in extract_text("a.pdf", make_pdf(["hello world"]))


@pytest.mark.parametrize("name,data", [
    ("a.txt", b""),
    ("a.py", b"   \n"),
    ("a.pdf", b"not a pdf"),
    ("a.jpeg", b"\xff\xd8"),
])
def test_empty_or_malformed_content_raises(name, data):
    with pytest.raises(SubmissionError):
        extract_text(name, data)


def test_size_limit():
    with pytest.raises(SubmissionError):
        extract_text("a.txt", b"x" * 11, max_bytes=10)
