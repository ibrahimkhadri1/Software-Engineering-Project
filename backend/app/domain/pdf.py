from io import BytesIO

from pypdf import PdfReader


class PdfError(ValueError):
    pass


def pdf_text(data: bytes, max_pages: int = 50) -> str:
    if not data.startswith(b"%PDF"):
        raise PdfError("not a PDF")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise PdfError("encrypted PDF")
        if len(reader.pages) > max_pages:
            raise PdfError(f"more than {max_pages} pages")
        text = "\n".join(page.extract_text() for page in reader.pages)
    except PdfError:
        raise
    except Exception as e:  # pypdf raises assorted error types on malformed input
        raise PdfError("unreadable PDF") from e
    if not text.strip():
        raise PdfError("no text found in the PDF")
    return text
