from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department
from hr_payroll.users.api.permissions import IsManagerOrAdmin

from .serializers import DepartmentSerializer


@extend_schema_view(
    list=extend_schema(tags=["Departments"]),
    retrieve=extend_schema(tags=["Departments"]),
    create=extend_schema(tags=["Departments"]),
    update=extend_schema(tags=["Departments"]),
    partial_update=extend_schema(tags=["Departments"]),
    destroy=extend_schema(tags=["Departments"]),
)
class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            # Allow Admin or HR to manage departments
            return [IsManagerOrAdmin()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="unassign-manager")
    @extend_schema(tags=["Departments"], request=None, responses={204: None})
    def unassign_manager(self, request, pk=None):  # pragma: no cover - simple utility
        dept = self.get_object()
        dept.manager = None
        dept.save(update_fields=["manager", "updated_at"])
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="assign-manager")
    @extend_schema(
        tags=["Departments"],
        description="Assign a manager to this department and grant Line Manager role.",
        request={
            "application/json": {
                "type": "object",
                "properties": {"employee_id": {"type": "integer"}},
                "required": ["employee_id"],
            }
        },
        responses={200: DepartmentSerializer},
    )
    def assign_manager(self, request, pk=None):
        dept = self.get_object()
        emp_id = request.data.get("employee_id")
        if not emp_id:
            return Response({"detail": "employee_id is required"}, status=400)
        try:
            employee = Employee.objects.get(pk=emp_id)
        except Employee.DoesNotExist:  # pragma: no cover - simple validation
            return Response({"detail": "Employee not found"}, status=404)
        dept.manager = employee
        dept.save(update_fields=["manager", "updated_at"])
        # Ensure Line Manager group assignment
        group, _ = Group.objects.get_or_create(name="Line Manager")
        if employee.user:
            employee.user.groups.add(group)
        serializer = self.get_serializer(dept)
        return Response(serializer.data, status=200)
