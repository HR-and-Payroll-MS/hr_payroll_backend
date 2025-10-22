from __future__ import annotations

import json
from typing import Any


def build_cv_resume_prompt(
    text: str, schema_json: dict[str, Any], baseline: dict[str, Any] | None = None
) -> str:
    """Build a robust prompt guiding the model to return structured CV JSON.

    Key guidance (defensive):
    - Names may appear near labels like: "Student", "Student Name", "Name",
      "Full Name", "Name of Student", "First Name"/"Last Name".
    - Do NOT treat institution headers as a person's name. Ignore lines with
      words like "University", "College", "Institute", "School", etc.
    - Prefer the candidate's name over supervisor, department, or institution.
    - Remove titles (Mr., Ms., Mrs., Dr.) from names. Trim extra whitespace.
    - For DOB, look for anchors: "Date of Birth", "DOB", "Born"; avoid
      education/employment date ranges.
    - For emails/phones, use standard patterns; avoid picking IDs.
    - Output ONLY a JSON object conforming to the given schema. Omit fields
      you are unsure about; never invent data.
    """

    baseline = baseline or {}
    schema_str = json.dumps(schema_json, ensure_ascii=False)
    baseline_str = json.dumps(baseline, ensure_ascii=False)

    guidance = (
        "You are a resume information extractor. "
        "Return ONLY a compact JSON object (no markdown) that conforms to the "
        "provided JSON schema. Be conservative and prefer precision.\n\n"
        "Rules for identifying the candidate's name:\n"
        "- Names can appear next to labels: 'Student', 'Student Name', 'Name', "
        "'Full Name', 'Name of Student', 'First Name', 'Last Name'.\n"
        "- Do NOT treat lines with 'University', 'College', 'Institute', "
        "'School', 'Faculty', 'Department' as a person's name.\n"
        "- Prefer the candidate over supervisors or departments.\n"
        "- Remove titles like Mr., Ms., Mrs., Dr. from the full name.\n"
        "- Provide 'full_name' and also split into 'first_name' and 'last_name'.\n\n"
        "Rules for other fields:\n"
        "- Date of birth must be anchored by 'Date of Birth', 'DOB', or 'Born'.\n"
        "- Avoid using date ranges from education or employment for DOB.\n"
        "- Emails/phones should match real-world formats; avoid IDs.\n"
        "- If a field is uncertain, omit it rather than guessing.\n\n"
        "Output requirements:\n"
        "- Output ONLY JSON matching the schema.\n"
        "- Omit fields you cannot determine with confidence.\n"
    )

    examples = (
        "Examples (do not copy text literally; follow the pattern):\n"
        "Input snippet: 'Student: John A. Doe' -> full_name='John A. Doe', "
        "first_name='John', last_name='Doe'.\n"
        "Input snippet: 'Name of Student: Sara K. Ali' -> full_name='Sara K. Ali'.\n"
        "Input snippet: 'University of Nairobi' -> NOT a person name.\n\n"
    )

    return (
        f"{guidance}"
        f"JSON schema: {schema_str}\n\n"
        f"Baseline values (may be incomplete): {baseline_str}\n\n"
        f"{examples}"
        f"Resume text begins:\n{text}\n\n"
        f"Return JSON now:"
    )
