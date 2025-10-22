from __future__ import annotations

import logging
from typing import Any

from hr_payroll.integrations.llm.client import get_llm_client_from_settings
from hr_payroll.integrations.llm.prompts import build_cv_resume_prompt

logger = logging.getLogger(__name__)


SCHEMA_JSON = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "national_id": {"type": "string"},
        "gender": {"type": "string"},
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": "string"},
                    "field": {"type": "string"},
                    "institution": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "gpa": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "organization": {"type": "string"},
                    "location": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}


def _build_prompt(text: str, baseline: dict[str, Any] | None = None) -> str:
    # Delegate to the dedicated prompt builder for clarity and reuse
    return build_cv_resume_prompt(text, SCHEMA_JSON, baseline=baseline)


def llm_map_cv_text_to_fields(
    text: str, baseline: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Map raw resume text to structured fields using a configured LLM.

    Returns None if LLM is disabled, misconfigured, or on any LLM error.
    """
    client = get_llm_client_from_settings()
    if client is None:
        return None
    prompt = _build_prompt(text, baseline=baseline)
    data = client.generate_json(prompt)
    if isinstance(data, dict):
        return data
    return None
