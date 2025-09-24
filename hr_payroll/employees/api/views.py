from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from ..models import Department, Employee, EmployeeDocument
from .permissions import IsAdminOrManagerCanWrite, IsSelfEmployeeOrElevated
from .serializers import (
    DepartmentSerializer,
    EmployeeDocumentSerializer,
    EmployeeSerializer,
)


class DepartmentViewSet(viewsets.ModelViewSet[Department]):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated & IsAdminOrManagerCanWrite]


class EmployeeViewSet(viewsets.ModelViewSet[Employee]):
    queryset = Employee.objects.select_related("user", "department")
    serializer_class = EmployeeSerializer
    # Authenticated users can read (limited by queryset), only elevated can write
    permission_classes = [IsAdminOrManagerCanWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, "is_staff", False) or (getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()):
            return qs
        # Regular employees: only see their own record
        return qs.filter(user=u)


class EmployeeDocumentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet[EmployeeDocument],
):
    queryset = EmployeeDocument.objects.select_related("employee", "employee__user")
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, "is_staff", False) or (getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()):
            return qs
        return qs.filter(employee__user=u)

    def perform_create(self, serializer):
        u = self.request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )
        employee = serializer.validated_data.get("employee")
        if not is_elevated and getattr(employee, "user_id", None) != getattr(u, "id", None):
            raise PermissionDenied("You can only upload documents for yourself.")
        serializer.save()
