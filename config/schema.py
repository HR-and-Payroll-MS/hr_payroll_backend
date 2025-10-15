"""Custom OpenAPI schema hooks for drf-spectacular.

This module adds human-friendly tag grouping so that all endpoints
appear under feature-specific sections instead of a single generic tag.
"""

from __future__ import annotations

from typing import Any

# Method names that contain operations in the OpenAPI path item
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


PATTERN_TAGS = [
    ("/api/v1/employee-documents", "Employee Documents"),
    ("/api/v1/employees", "Employees"),
    ("/api/v1/departments", "Departments"),
    ("/api/v1/auth/jwt", "JWT Authentication"),
    ("/api/v1/auth/users", "User Management"),
    ("/api/v1/auth/login", "Session Auth"),
    ("/api/v1/auth/logout", "Session Auth"),
    ("/api/v1/auth/password", "Session Auth"),
    ("/api/v1/auth/", "Authentication"),
    ("/api/v1/users", "Users"),
    ("/api/v1/positions", "Positions"),
]

ALL_TAGS = [t for _, t in PATTERN_TAGS]


def assign_group_tag(path: str) -> str | None:
    """Return the first matching tag name for a given path."""
    for prefix, tag in PATTERN_TAGS:
        if path.startswith(prefix):
            return tag
    return None


def group_tags(result: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Post-processing hook to force consistent tag grouping.

    For every operation we overwrite/define the ``tags`` list with exactly one
    logical group (Employees, Departments, Users, Authentication, etc.).  This
    keeps the Swagger UI navigation nicely partitioned after consolidating to
    versioned routes.
    """
    paths = result.get("paths", {})
    for path, path_item in paths.items():  # type: ignore[assignment]
        tag = assign_group_tag(path)
        if not tag:
            continue
        for method, op_obj in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(op_obj, dict):  # safety guard
                continue
            op_obj["tags"] = [tag]

    # Ensure declared tags list contains all groups we used (order preserved)
    existing = {t.get("name") for t in result.get("tags", [])}
    tag_list = result.setdefault("tags", [])
    for tag in ALL_TAGS:
        if tag not in existing:
            tag_list.append({"name": tag})
    return result
