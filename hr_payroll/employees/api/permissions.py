"""Permission classes for Employees API."""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission
from typing import Any


def _user_in_groups(user, names: list[str]) -> bool:
    groups = getattr(user, "groups", None)
    return bool(groups and groups.filter(name__in=names).exists())


class IsAdminOrManagerCanWrite(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        # write methods
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        is_elevated = bool(getattr(u, "is_staff", False))
        if not is_elevated:
            is_elevated = _user_in_groups(u, ["Admin", "Manager"])  # HR Manager
        return is_elevated


class IsSelfEmployeeOrElevated(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        # Elevated users can write
        is_elevated = bool(getattr(u, "is_staff", False))
        if not is_elevated:
            is_elevated = _user_in_groups(u, ["Admin", "Manager"])  # HR Manager
        if is_elevated:
            return True
        # Non-elevated: only allow modifications to own resources
        # Works for Employee (has user_id) and EmployeeDocument (has employee.user_id)
        if hasattr(obj, "user_id"):
            return getattr(obj, "user_id", None) == getattr(u, "id", None)
        if hasattr(obj, "employee") and hasattr(obj.employee, "user_id"):
            return getattr(obj.employee, "user_id", None) == getattr(u, "id", None)
        return False


class IsAdminOrHROrLineManagerScopedWrite(BasePermission):
    """Allow writes for Admin/HR globally; allow Line Managers only for their scope.

    Scope definition:
    - If the target is an Employee: permitted when request.user's Employee is either
      the target's department.manager OR the target's line_manager.
    - If the target has an 'employee' attribute (e.g., JobHistory, Contract, EmployeeDocument):
      apply the same rule to target.employee.
    """

    def has_permission(self, request, view) -> bool:
        # Read always allowed for authenticated users; writes guarded below
        if request.method in SAFE_METHODS:
            return bool(getattr(request.user, "is_authenticated", False))
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"]):
            return True
        # For line managers, object-level checks will decide; allow to proceed
        return _user_in_groups(u, ["Line Manager"])  # may be narrowed by object check

    def has_object_permission(self, request, view, obj: Any) -> bool:  # noqa: C901
        if request.method in SAFE_METHODS:
            return True
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        # Admin/HR bypass
        if getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"]):
            return True
        if not _user_in_groups(u, ["Line Manager"]):
            return False
        # Resolve request user's employee record
        req_emp = getattr(u, "employee", None)
        if req_emp is None:
            return False
        # Determine target employee
        target_emp = None
        if hasattr(obj, "user_id") and hasattr(obj, "department_id"):
            target_emp = obj
        elif hasattr(obj, "employee"):
            target_emp = getattr(obj, "employee", None)
        # If still unknown, deny
        if target_emp is None:
            return False
        # Allow if line manager directly
        if getattr(target_emp, "line_manager_id", None) == getattr(req_emp, "id", None):
            return True
        # Allow if department manager
        dept = getattr(target_emp, "department", None)
        if dept and getattr(dept, "manager_id", None) == getattr(req_emp, "id", None):
            return True
        return False
