from __future__ import annotations

import copy
from typing import Any

from hr_payroll.org.models import OrganizationPolicy
from hr_payroll.policies.defaults import get_default_policy_document


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base (dict-only), returning a new dict."""

    out: dict[str, Any] = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_policy_document(org_id: int = 1) -> dict[str, Any]:
    """Return the organization policy document for `org_id`.

    - If a policy row exists, return defaults merged with the stored document.
    - Otherwise return the default policy document.

    This mirrors the frontend `initialPolicies` shape.
    """

    defaults = get_default_policy_document()

    row = OrganizationPolicy.objects.filter(org_id=org_id).first()
    if not row or not isinstance(row.document, dict):
        return defaults

    return _deep_merge(defaults, row.document)
