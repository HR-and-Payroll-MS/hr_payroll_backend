from rest_framework.permissions import BasePermission

ELEVATED_GROUPS = {"Admin", "Manager"}


def _has_employee_or_staff(user) -> bool:
    """Helper to assert user is staff/superuser or has an employee profile."""

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return bool(getattr(user, "employee", None))


def _in_groups(user, names: set[str]) -> bool:
    groups = getattr(user, "groups", None)
    if not groups:
        return False
    return groups.filter(name__in=names).exists()


class IsManagerOrAdmin(BasePermission):
    """Allow access to staff/superusers, or Admin/Manager users who have an employee profile."""

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_superuser", False) or getattr(u, "is_staff", False):
            return True
        if not _has_employee_or_staff(u):
            return False
        return _in_groups(u, ELEVATED_GROUPS)
