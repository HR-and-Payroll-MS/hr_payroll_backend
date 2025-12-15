"""Permission classes for Employees API."""

from collections.abc import Iterable
from typing import Any

from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission

ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_PAYROLL = "Payroll"
ROLE_LINE_MANAGER = "Line Manager"


def _user_in_groups(user, names: Iterable[str]) -> bool:
    groups = getattr(user, "groups", None)
    names_list = list(names)
    if not groups or not names_list:
        return False
    return groups.filter(name__in=names_list).exists()


def _is_staff_or_role(user, roles: Iterable[str]) -> bool:
    return bool(getattr(user, "is_staff", False)) or _user_in_groups(user, roles)


def _target_employee_from_object(obj: Any):
    if hasattr(obj, "user_id") and hasattr(obj, "department_id"):
        return obj
    if hasattr(obj, "employee"):
        return getattr(obj, "employee", None)
    return None


def _is_self_employee(user, obj: Any) -> bool:
    if hasattr(obj, "user_id"):
        return getattr(obj, "user_id", None) == getattr(user, "id", None)
    employee = getattr(obj, "employee", None)
    if employee and hasattr(employee, "user_id"):
        return getattr(employee, "user_id", None) == getattr(user, "id", None)
    return False


def _line_manager_in_scope(user, obj: Any) -> bool:
    target_employee = _target_employee_from_object(obj)
    if target_employee is None:
        return False
    req_emp = getattr(user, "employee", None)
    if req_emp is None:
        return False
    is_direct_manager = getattr(target_employee, "line_manager_id", None) == getattr(
        req_emp, "id", None
    )
    dept = getattr(target_employee, "department", None)
    is_dept_manager = bool(
        dept and getattr(dept, "manager_id", None) == getattr(req_emp, "id", None)
    )
    return bool(is_direct_manager or is_dept_manager)


class _RolePermission(BasePermission):
    """Base helper to gate access by role names."""

    allowed_roles: tuple[str, ...] = ()
    allow_staff: bool = True

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return False
        if self.allow_staff and getattr(user, "is_staff", False):
            return True
        return _user_in_groups(user, self.allowed_roles)


class IsAdminOrManagerCanWrite(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        return _is_staff_or_role(u, [ROLE_ADMIN, ROLE_MANAGER])


class IsSelfEmployeeOrElevated(BasePermission):
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if _is_staff_or_role(u, [ROLE_ADMIN, ROLE_MANAGER]):
            return True
        is_line_manager = _user_in_groups(u, [ROLE_LINE_MANAGER])
        in_scope = bool(is_line_manager and _line_manager_in_scope(u, obj))
        is_self = _is_self_employee(u, obj)
        if request.method in SAFE_METHODS:
            return bool(in_scope or is_self)
        if in_scope:
            return True
        return is_self


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
        if _is_staff_or_role(u, [ROLE_ADMIN, ROLE_MANAGER]):
            return True
        return _user_in_groups(u, [ROLE_LINE_MANAGER])

    def has_object_permission(self, request, view, obj: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if _is_staff_or_role(u, [ROLE_ADMIN, ROLE_MANAGER]):
            return True
        if not _user_in_groups(u, [ROLE_LINE_MANAGER]):
            return False
        return _line_manager_in_scope(u, obj)


class IsAdminOrManagerOnly(_RolePermission):
    """Allow access only to Admin/Manager/Staff users."""

    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER)


class IsAdminOrPayrollOnly(_RolePermission):
    """Restrict writes to Admin/Payroll roles (with staff overrides)."""

    allowed_roles = (ROLE_ADMIN, ROLE_PAYROLL)
