from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import ClassVar

from app.domain.pdf import PdfError, pdf_text

ALLOWED_FILETYPES = frozenset({".pdf", ".py", ".java", ".txt"})


class SubmissionError(ValueError):
    pass


@dataclass
class SubmissionStatus:
    file_type: str
    is_accepted: bool
    error: str | None = None
    allowed_filetypes: ClassVar[frozenset[str]] = ALLOWED_FILETYPES

    @property
    def is_rejected(self) -> bool:
        return not self.is_accepted

    @staticmethod
    def check_filetype(filename: str) -> bool:
        return PurePosixPath(filename).suffix.lower() in ALLOWED_FILETYPES

    @classmethod
    def for_submission(cls, filenames: list[str], body: str | None = None) -> "SubmissionStatus":
        suffixes = sorted({PurePosixPath(name).suffix.lower() or "no extension" for name in filenames})
        if not filenames:
            if body and body.strip():
                return cls("online_text", True)
            return cls("", False, "empty submission")
        if not all(cls.check_filetype(name) for name in filenames):
            return cls(", ".join(suffixes), False, "unsupported file type")
        return cls(", ".join(suffixes), True)


def extract_text(filename: str, data: bytes, max_bytes: int = 5_000_000, max_pages: int = 50) -> str:
    if len(data) > max_bytes:
        raise SubmissionError("file too large")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in ALLOWED_FILETYPES:
        raise SubmissionError("unsupported file type")
    try:
        if suffix == ".pdf":
            text = pdf_text(data, max_pages)
        else:  # Windows PowerShell 5.1 redirects write UTF-16 with a byte-order mark
            text = data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig", errors="replace")
    except PdfError as e:
        raise SubmissionError(str(e)) from e
    text = text.replace("\x00", "")  # PostgreSQL text columns reject NUL characters
    if not text.strip():
        raise SubmissionError("empty file")
    return text
