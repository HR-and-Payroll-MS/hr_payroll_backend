from datetime import date

from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday
from hr_payroll.org.models import Department
from hr_payroll.org.models import OrganizationPolicy
from hr_payroll.policies import get_policy_document
from hr_payroll.users.api.permissions import IsManagerOrAdmin

from .serializers import DepartmentSerializer


def _parse_iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _sync_public_holidays_from_policy(holiday_policy: dict) -> None:
    # Only sync date-based (fixed/company) holidays; floating holidays are rule-based.
    for key in ("fixedHolidays", "companyHolidays"):
        items = holiday_policy.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            holiday_date = _parse_iso_date(item.get("date"))
            name = item.get("name")
            if not holiday_date or not isinstance(name, str) or not name.strip():
                continue
            PublicHoliday.objects.get_or_create(
                name=name.strip(),
                start_date=holiday_date,
                end_date=holiday_date,
                year=holiday_date.year,
            )


def _sync_leave_types_from_policy(leave_policy: dict) -> None:
    items = leave_policy.get("leaveTypes")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        paid = item.get("paid")
        is_paid = bool(paid) if paid is not None else True

        # LeaveType requires color_code; frontend policy doesn't include it.
        obj, created = LeaveType.objects.get_or_create(
            name=name.strip(),
            defaults={
                "is_paid": is_paid,
                "unit": LeaveType.Unit.DAYS,
                "color_code": "#00FF00",
                "description": "",
            },
        )
        if not created and obj.is_paid != is_paid:
            obj.is_paid = is_paid
            obj.save(update_fields=["is_paid"])


def _sync_departments_from_policy(job_structure_policy: dict) -> None:
    items = job_structure_policy.get("departments")
    if not isinstance(items, list):
        return
    for name in items:
        if not isinstance(name, str) or not name.strip():
            continue
        Department.objects.get_or_create(name=name.strip())


def _sync_backend_resources_from_policy_document(doc: dict) -> None:
    if not isinstance(doc, dict):
        return
    holiday_policy = doc.get("holidayPolicy")
    if isinstance(holiday_policy, dict):
        _sync_public_holidays_from_policy(holiday_policy)
    leave_policy = doc.get("leavePolicy")
    if isinstance(leave_policy, dict):
        _sync_leave_types_from_policy(leave_policy)
    job_structure_policy = doc.get("jobStructurePolicy")
    if isinstance(job_structure_policy, dict):
        _sync_departments_from_policy(job_structure_policy)


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


def _can_write_org_policies(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    names = set(user.groups.values_list("name", flat=True))
    # Frontend has HR Manager and Payroll Officer flows that both expect updates.
    return bool(names.intersection({"Admin", "Manager", "Payroll"}))


@extend_schema(tags=["Organization • Policies"])
class OrganizationPoliciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, org_id: int):
        return Response(get_policy_document(org_id=org_id), status=200)

    def put(self, request, org_id: int):
        if not _can_write_org_policies(request.user):
            return Response({"detail": "Forbidden"}, status=403)
        if not isinstance(request.data, dict):
            return Response({"detail": "Expected JSON object"}, status=400)

        # Store as-is; GET will merge with defaults.
        obj, _created = OrganizationPolicy.objects.update_or_create(
            org_id=org_id,
            defaults={"document": request.data},
        )

        _sync_backend_resources_from_policy_document(request.data)
        return Response(get_policy_document(org_id=obj.org_id), status=200)


@extend_schema(tags=["Organization • Policies"])
class OrganizationPolicySectionView(APIView):
    permission_classes = [IsAuthenticated]

    _allowed_sections = {
        "general",
        "attendancePolicy",
        "leavePolicy",
        "holidayPolicy",
        "shiftPolicy",
        "overtimePolicy",
        "disciplinaryPolicy",
        "jobStructurePolicy",
        "salaryStructurePolicy",
    }

    def get(self, request, org_id: int, section: str):
        if section not in self._allowed_sections:
            return Response({"detail": "Unknown section"}, status=404)
        doc = get_policy_document(org_id=org_id)
        return Response({section: doc.get(section)}, status=200)

    def put(self, request, org_id: int, section: str):
        if section not in self._allowed_sections:
            return Response({"detail": "Unknown section"}, status=404)
        if not _can_write_org_policies(request.user):
            return Response({"detail": "Forbidden"}, status=403)
        if not isinstance(request.data, dict):
            return Response({"detail": "Expected JSON object"}, status=400)

        # Frontend sends payload as { [section]: policyData[section] }
        section_payload = request.data.get(section, request.data)

        obj, _created = OrganizationPolicy.objects.get_or_create(
            org_id=org_id, defaults={"document": {}}
        )
        stored = obj.document if isinstance(obj.document, dict) else {}
        stored = dict(stored)
        stored[section] = section_payload
        obj.document = stored
        obj.save(update_fields=["document", "updated_at"])

        # Sync any supported backend resources impacted by this section.
        if section == "holidayPolicy" and isinstance(section_payload, dict):
            _sync_public_holidays_from_policy(section_payload)
        elif section == "leavePolicy" and isinstance(section_payload, dict):
            _sync_leave_types_from_policy(section_payload)
        elif section == "jobStructurePolicy" and isinstance(section_payload, dict):
            _sync_departments_from_policy(section_payload)

        # Return merged doc so missing keys are always present.
        return Response(get_policy_document(org_id=org_id), status=200)
