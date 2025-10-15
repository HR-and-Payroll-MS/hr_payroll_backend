"""CV parsing utilities.

This module provides a best-effort extraction of basic profile fields from a CV.

Contract:
- Input: bytes (PDF) and optional filename.
- Output: dict with any of the keys: full_name, first_name, last_name,
  email, phone, address, date_of_birth, national_id, gender.

Implementation details:
- Tries to use Docling if available (preferred for robust parsing).
- Falls back to a light-weight PDF text extraction and regex heuristics.
- Never raises on parse errors; returns {} when nothing is found.
"""

from __future__ import annotations

import io
import re
from contextlib import suppress
from typing import Any

try:  # optional dependency
    from docling.document import Document  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional
    Document = None  # type: ignore[assignment]

try:  # optional fallback
    import PyPDF2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional
    PyPDF2 = None  # type: ignore[assignment]


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF in-memory.

    Returns an empty string if no extractor is available or parsing fails.
    """
    if Document is not None:
        with suppress(Exception):
            doc = Document.from_bytes(pdf_bytes)
            return doc.text or ""

    if PyPDF2 is not None:
        with suppress(Exception):
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            out: list[str] = []
            for page in getattr(reader, "pages", []) or []:
                with suppress(Exception):
                    out.append((page.extract_text() or "").strip())
            return "\n".join([t for t in out if t])

    return ""


def _split_name(full_name: str) -> tuple[str, str]:
    full = re.sub(r"\s+", " ", full_name.strip())
    if not full:
        return "", ""
    parts = full.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d \-()]{6,}\d)")
DOB_RE = re.compile(
    r"\b(?:(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
)
NAME_MAX_TOKENS = 5


def parse_cv(pdf_bytes: bytes, filename: str | None = None) -> dict[str, Any]:
    """Parse a CV PDF and return extracted fields.

    Best-effort only; callers should only use values to prefill optional inputs
    and allow users to review/edit.
    """
    text = _extract_text_from_pdf_bytes(pdf_bytes)
    if not text:
        return {}

    data: dict[str, Any] = {}

    m = EMAIL_RE.search(text)
    if m:
        data["email"] = m.group(0)

    m = PHONE_RE.search(text)
    if m:
        data["phone"] = m.group(1).strip()

    m = DOB_RE.search(text)
    if m:
        data["date_of_birth"] = m.group(0)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        first_line = lines[0]
        if (
            not EMAIL_RE.search(first_line)
            and len(first_line.split()) <= NAME_MAX_TOKENS
        ):
            data["full_name"] = first_line
            fn, ln = _split_name(first_line)
            data["first_name"], data["last_name"] = fn, ln

    return data
