"""CV parsing utilities.

This module provides a best-effort extraction of basic profile fields from a CV.

Contract:
- Input: bytes (PDF) and optional filename.
- Output: dict with any of the keys: full_name, first_name, last_name,
  email, phone, address, date_of_birth, national_id, gender.

Implementation details:
- Uses pdfminer.six for robust text extraction when available.
- Falls back to a light-weight pypdf text extraction and regex heuristics.
- Never raises on parse errors; returns {} when nothing is found.
"""

from __future__ import annotations

import io
import logging
import os
import re
from contextlib import suppress
from typing import TYPE_CHECKING
from typing import Any

try:  # optional dependency (preferred)
    from pdfminer.high_level import extract_text  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional
    extract_text = None  # type: ignore[assignment]

try:  # optional fallback
    from pypdf import PdfReader  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional
    PdfReader = None  # type: ignore[assignment]

# Optional OCR dependencies (used only when enabled)
try:  # pragma: no cover - optional runtime dependency
    import pytesseract  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    pytesseract = None  # type: ignore[assignment]

try:  # pragma: no cover - optional runtime dependency
    from pdf2image import convert_from_bytes  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    convert_from_bytes = None  # type: ignore[assignment]


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF in-memory.

    Returns an empty string if no extractor is available or parsing fails.
    """
    if extract_text is not None:
        with suppress(Exception):
            return extract_text(io.BytesIO(pdf_bytes)) or ""

    if PdfReader is not None:
        with suppress(Exception):
            reader = PdfReader(io.BytesIO(pdf_bytes))
            out: list[str] = []
            for page in getattr(reader, "pages", []) or []:
                with suppress(Exception):
                    out.append((page.extract_text() or "").strip())
            return "\n".join([t for t in out if t])

    return ""


def _ocr_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """OCR a PDF by rasterizing to images and running Tesseract.

    Returns an empty string if OCR tooling isn't available or OCR fails.
    Limits pages for performance.
    """
    if pytesseract is None or convert_from_bytes is None:
        return ""
    text_chunks: list[str] = []
    # Heuristic: OCR first N pages to keep latency bounded
    max_pages = int(os.environ.get("CV_OCR_MAX_PAGES", "3"))
    dpi = int(os.environ.get("CV_OCR_DPI", "300"))
    lang = os.environ.get("CV_OCR_LANG", "eng")
    with suppress(Exception):
        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            fmt="PNG",
            first_page=1,
            # last_page is inclusive; we don't know pages here, so slice after
        )
        for idx, img in enumerate(images):
            if idx >= max_pages:
                break
            with suppress(Exception):
                txt = pytesseract.image_to_string(img, lang=lang) or ""
                if txt.strip():
                    text_chunks.append(txt)
    return "\n".join(text_chunks)


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


logger = logging.getLogger(__name__)

dj_settings = None  # type: ignore[assignment]
try:  # optional: module can be imported before Django settings are ready
    from django.conf import settings as _dj_settings  # type: ignore[import-not-found]

    dj_settings = _dj_settings  # type: ignore[assignment]
except Exception:  # pragma: no cover - optional import  # noqa: BLE001
    # If Django isn't configured, fall back to env-only debug control.
    dj_settings = None  # type: ignore[assignment]

# For type-checkers only; runtime import done inside the function
if TYPE_CHECKING:  # pragma: no cover - typing only
    from hr_payroll.employees.services.cv_llm_mapper import (  # noqa: F401
        llm_map_cv_text_to_fields as _llm_map_cv_text_to_fields_type,
    )


def _cv_debug_enabled() -> bool:
    return bool(
        (getattr(dj_settings, "DEBUG", False) if dj_settings is not None else False)
        or os.environ.get("ENABLE_CV_DEBUG") == "1"
    )


def _cv_ocr_enabled() -> bool:
    # Feature flag: enable OCR fallback when primary extractors return no text
    if dj_settings is not None:
        if getattr(dj_settings, "CV_PARSER_OCR_ENABLED", False):
            return True
    return os.environ.get("ENABLE_CV_OCR") == "1"


def _cv_ocr_min_text_chars() -> int:
    """Minimum primary text length before we consider it 'empty' and try OCR.

    Allows triggering OCR even when extractors return a few stray characters
    (e.g., scanned PDFs sometimes yield 1-2 control chars). Defaults to 50.
    """
    # Prefer Django settings if available
    if dj_settings is not None:
        val = getattr(dj_settings, "CV_PARSER_OCR_MIN_TEXT_CHARS", None)
        if isinstance(val, int) and val >= 0:
            return val
    # Fallback to environment variable
    try:
        return max(0, int(os.environ.get("CV_OCR_MIN_TEXT_CHARS", "50")))
    except Exception:  # noqa: BLE001
        return 50


def _cv_llm_enabled() -> bool:
    # Feature flag: enable LLM post-processing mapping
    if dj_settings is not None:
        if getattr(dj_settings, "CV_PARSER_LLM_ENABLED", False):
            return True
    return os.environ.get("ENABLE_CV_LLM") == "1"


def _cv_llm_override_fields() -> set[str]:
    """Fields the LLM is allowed to override from heuristics.

    Defaults to name-related fields and DOB to avoid common header mixups.
    Configure via:
    - settings.CV_PARSER_LLM_OVERRIDE_FIELDS = ["full_name", ...]
    - or env CV_LLM_OVERRIDE_FIELDS="full_name,first_name,last_name,date_of_birth"
    """
    default = {"full_name", "first_name", "last_name", "date_of_birth"}
    if dj_settings is not None:
        vals = getattr(dj_settings, "CV_PARSER_LLM_OVERRIDE_FIELDS", None)
        if isinstance(vals, (list, tuple, set)):
            return {str(v) for v in vals}
    env_val = os.environ.get(
        "CV_LLM_OVERRIDE_FIELDS",
        "full_name,first_name,last_name,date_of_birth",
    )
    try:
        return {v.strip() for v in env_val.split(",") if v.strip()}
    except Exception:  # noqa: BLE001 - fallback to default
        return default


HEADER_NO_NAME_KEYWORDS = (
    "university",
    "college",
    "institute",
    "school",
    "faculty",
    "department",
    "curriculum vitae",
    "resume",
)


ALL_CAPS_RATIO_THRESHOLD = 0.9
MIN_NAME_TOKENS = 2


def _is_probable_person_name(line: str) -> bool:  # noqa: PLR0911 - small guard clauses
    """Return True if the line looks like a person's name, not a header.

    Heuristics: avoid common academic headers, all-caps lines, emails, digits;
    require 2-5 tokens mostly Title Case.
    """
    txt = line.strip()
    if not txt:
        return False
    low = txt.lower()
    if any(k in low for k in HEADER_NO_NAME_KEYWORDS):
        return False
    if EMAIL_RE.search(txt):
        return False
    tokens = [t for t in txt.split() if t]
    if not (MIN_NAME_TOKENS <= len(tokens) <= NAME_MAX_TOKENS):
        return False
    if any(any(ch.isdigit() for ch in t) for t in tokens):
        return False
    letters = [ch for ch in txt if ch.isalpha()]
    if (
        letters
        and (sum(ch.isupper() for ch in letters) / len(letters))
        > ALL_CAPS_RATIO_THRESHOLD
    ):
        # Likely an all-caps section header
        return False
    title_like = sum(1 for t in tokens if t[0].isalpha() and t[0].isupper())
    return not (title_like < len(tokens) - 1)


def parse_cv(pdf_bytes: bytes, filename: str | None = None) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - acceptable orchestration for parse flow
    """Parse a CV PDF and return extracted fields.

    Best-effort only; callers should only use values to prefill optional inputs
    and allow users to review/edit.
    """
    text = _extract_text_from_pdf_bytes(pdf_bytes) or ""
    ocr_used = False
    text_len = len(text)
    min_chars = _cv_ocr_min_text_chars()
    # Trigger OCR if primary extraction is empty OR trivially small
    if _cv_ocr_enabled() and text_len < max(1, min_chars):
        # Attempt OCR fallback
        if _cv_debug_enabled():
            logger.info(
                (
                    "CV parse: primary text tiny (chars=%s < %s), trying OCR "
                    "(file=%s, size=%s)"
                ),
                text_len,
                min_chars,
                filename,
                len(pdf_bytes),
            )
        with suppress(Exception):
            ocr_text = _ocr_text_from_pdf_bytes(pdf_bytes)
            ocr_used = bool(ocr_text)
            if _cv_debug_enabled():
                logger.info(
                    "CV parse: OCR fallback %s (file=%s, chars=%s)",
                    "succeeded" if ocr_text else "returned-empty",
                    filename,
                    len(ocr_text) if ocr_text else 0,
                )
            if ocr_text:
                text = ocr_text
    if not text:
        # Log in debug to aid troubleshooting when extraction returns empty
        if _cv_debug_enabled():
            logger.debug(
                "CV parse: no text extracted (file=%s, size=%s)",
                filename,
                len(pdf_bytes),
            )
        if _cv_debug_enabled():
            logger.warning(
                (
                    "CV parse: no text extracted after %s (file=%s). "
                    "If scan, try higher DPI or more pages."
                ),
                "OCR" if ocr_used else "primary extraction",
                filename,
            )
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
        # Use first plausible name within the first few lines to avoid headers
        candidate = None
        for ln in lines[:10]:
            if _is_probable_person_name(ln):
                candidate = ln
                break
        if candidate:
            data["full_name"] = candidate
            fn, ln = _split_name(candidate)
            data["first_name"], data["last_name"] = fn, ln

    # Debug log the extracted summary (avoid printing raw text)
    # Optional: LLM post-processing to enrich mapping of fields
    if _cv_llm_enabled():
        try:
            from hr_payroll.employees.services.cv_llm_mapper import (  # noqa: PLC0415
                llm_map_cv_text_to_fields,
            )
        except Exception:  # noqa: BLE001 - optional import path
            llm_map_cv_text_to_fields = None  # type: ignore[assignment]
        llm_data = None
        if llm_map_cv_text_to_fields is not None:
            llm_data = llm_map_cv_text_to_fields(text, baseline=data)
        if llm_data:
            override = _cv_llm_override_fields()
            overridden: list[str] = []
            for k, v in llm_data.items():
                if not v:
                    continue
                if (k not in data) or (k in override):
                    prev = data.get(k)
                    data[k] = v
                    if prev != v:
                        overridden.append(k)
            if _cv_debug_enabled():
                logger.info(
                    "CV LLM mapping applied (override=%s): overridden=%s",
                    sorted(override),
                    overridden,
                )

    # Debug log the extracted summary (avoid printing raw text)
    if _cv_debug_enabled():
        logger.info(
            "CV parse extracted: %s (file=%s, chars=%s, ocr=%s)",
            data,
            filename,
            len(text),
            ocr_used,
        )
    return data
