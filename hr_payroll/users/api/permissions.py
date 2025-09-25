from rest_framework.permissions import BasePermission


class IsManagerOrAdmin(BasePermission):
    """Allow access only to staff or users in Admin/Manager groups."""

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_staff", False):
            return True
        groups = getattr(u, "groups", None)
        return bool(groups and groups.filter(name__in=["Admin", "Manager"]).exists())
