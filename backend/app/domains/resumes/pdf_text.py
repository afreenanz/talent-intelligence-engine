"""PDF -> clean text. No LLM involved, and every failure maps to a clear, user-facing reason."""

import io
import re
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PAGES = 10
MAX_TEXT_CHARS = 30_000
MIN_TEXT_CHARS = 80  # below this, the PDF is almost certainly a scanned image


class ResumeTextError(Exception):
    """The PDF can't be turned into usable text. The message is safe to show the user."""


@dataclass(frozen=True)
class ExtractedText:
    text: str
    page_count: int
    truncated: bool


def looks_like_pdf(data: bytes) -> bool:
    # Magic bytes, not the client-supplied Content-Type, which is trivially spoofed.
    return data[:1024].lstrip().startswith(b"%PDF-")


def extract_text(data: bytes) -> ExtractedText:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ResumeTextError("The PDF is password-protected. Upload an unprotected copy.")
        page_count = len(reader.pages)
        if page_count == 0:
            raise ResumeTextError("The PDF has no pages.")
        if page_count > MAX_PAGES:
            raise ResumeTextError(f"The PDF has {page_count} pages; the limit is {MAX_PAGES}.")
        raw = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ResumeTextError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ResumeTextError("The file could not be read as a PDF (it may be corrupted).") from exc

    text = clean_resume_text(raw)
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeTextError(
            "No readable text was found. Scanned/image-only PDFs are not supported (no OCR)."
        )
    truncated = len(text) > MAX_TEXT_CHARS
    return ExtractedText(text=text[:MAX_TEXT_CHARS], page_count=page_count, truncated=truncated)


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANKS = re.compile(r"\n{3,}")


def clean_resume_text(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "devel-\noper" -> "developer"
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()
