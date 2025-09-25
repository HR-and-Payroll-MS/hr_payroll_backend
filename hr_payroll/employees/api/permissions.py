"""Permission classes for Employees API."""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission


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
            groups = getattr(u, "groups", None)
            is_elevated = bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists(),
            )
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
            groups = getattr(u, "groups", None)
            is_elevated = bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists(),
            )
        if is_elevated:
            return True
        # Non-elevated: only allow modifications to own resources
        # Works for Employee (has user_id) and EmployeeDocument (has employee.user_id)
        if hasattr(obj, "user_id"):
            return getattr(obj, "user_id", None) == getattr(u, "id", None)
        if hasattr(obj, "employee") and hasattr(obj.employee, "user_id"):
            return getattr(obj.employee, "user_id", None) == getattr(u, "id", None)
        return False
