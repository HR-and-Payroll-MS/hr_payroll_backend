"""Permission classes for Employees API."""

from typing import Any

from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission


def _user_in_groups(user, names: list[str]) -> bool:
    groups = getattr(user, "groups", None)
    return bool(groups and groups.filter(name__in=names).exists())


class IsAdminOrManagerCanWrite(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        is_elevated = bool(getattr(u, "is_staff", False))
        if not is_elevated:
            is_elevated = _user_in_groups(u, ["Admin", "Manager"])
        return is_elevated


class IsSelfEmployeeOrElevated(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        is_elevated = bool(getattr(u, "is_staff", False))
        if not is_elevated:
            is_elevated = _user_in_groups(u, ["Admin", "Manager"])
        if is_elevated:
            return True
        if hasattr(obj, "user_id"):
            return getattr(obj, "user_id", None) == getattr(u, "id", None)
        if hasattr(obj, "employee") and hasattr(obj.employee, "user_id"):
            return getattr(obj.employee, "user_id", None) == getattr(u, "id", None)
        return False


class IsAdminOrHROrLineManagerScopedWrite(BasePermission):
    """Allow writes for Admin/HR globally; Line Managers only within scope.

    Scope definition:
    - If target is an Employee: permit when request.user.employee is the
      department manager or the target's line manager.
    - If target has an 'employee' attribute (JobHistory, Contract,
      EmployeeDocument): apply the same rule to target.employee.
    """

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return bool(getattr(request.user, "is_authenticated", False))
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"]):
            return True

        return _user_in_groups(u, ["Line Manager"])

    def has_object_permission(self, request, view, obj: Any) -> bool:  # noqa: PLR0911
        if request.method in SAFE_METHODS:
            return True
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"]):
            return True
        if not _user_in_groups(u, ["Line Manager"]):
            return False
        req_emp = getattr(u, "employee", None)
        if req_emp is None:
            return False
        target_emp = None
        if hasattr(obj, "user_id") and hasattr(obj, "department_id"):
            target_emp = obj
        elif hasattr(obj, "employee"):
            target_emp = getattr(obj, "employee", None)
        if target_emp is None:
            return False
        is_line_manager = getattr(target_emp, "line_manager_id", None) == getattr(
            req_emp, "id", None
        )
        dept = getattr(target_emp, "department", None)
        is_dept_manager = bool(
            dept and getattr(dept, "manager_id", None) == getattr(req_emp, "id", None)
        )
        return bool(is_line_manager or is_dept_manager)
