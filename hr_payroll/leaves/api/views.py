import contextlib

from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from hr_payroll.audit.utils import log_action
from hr_payroll.employees.api.permissions import ROLE_ADMIN
from hr_payroll.employees.api.permissions import ROLE_LINE_MANAGER
from hr_payroll.employees.api.permissions import ROLE_MANAGER
from hr_payroll.employees.api.permissions import IsAdminOrManagerOnly
from hr_payroll.employees.api.permissions import _user_in_groups
from hr_payroll.employees.models import Employee
from hr_payroll.leaves.api.serializers import BalanceHistorySerializer
from hr_payroll.leaves.api.serializers import EmployeeBalanceSerializer
from hr_payroll.leaves.api.serializers import LeavePolicySerializer
from hr_payroll.leaves.api.serializers import LeaveRequestSerializer
from hr_payroll.leaves.api.serializers import LeaveTypeSerializer
from hr_payroll.leaves.api.serializers import PublicHolidaySerializer
from hr_payroll.leaves.models import BalanceHistory
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday


def _is_leave_admin(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or _user_in_groups(user, [ROLE_ADMIN, ROLE_MANAGER])
    )


def _managed_employee_ids(user) -> list[int]:
    employee = getattr(user, "employee", None)
    if employee is None:
        return []
    ids: set[int] = set()
    dept_ids = list(employee.managed_departments.values_list("id", flat=True))
    if dept_ids:
        ids.update(
            Employee.objects.filter(department_id__in=dept_ids).values_list(
                "id", flat=True
            )
        )
    dept_id = getattr(employee, "department_id", None)
    if dept_id:
        ids.update(
            Employee.objects.filter(department_id=dept_id).values_list("id", flat=True)
        )
    ids.update(
        Employee.objects.filter(line_manager_id=employee.id).values_list(
            "id", flat=True
        )
    )
    if employee.id:
        ids.add(employee.id)
    return list(ids)


class LeavesPlaceholderViewSet(viewsets.ViewSet):
    """
    Placeholder ViewSet to show 'leaves' in API root.
    Actual endpoints are nested under /api/v1/leaves/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None  # Explicitly set to avoid drf_spectacular warning

    @extend_schema(exclude=True)
    def list(self, request):
        return Response({"message": "Leaves API Root"})


class LeaveTypeViewSet(viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAdminOrManagerOnly]


class LeavePolicyViewSet(viewsets.ModelViewSet):
    queryset = LeavePolicy.objects.all()
    serializer_class = LeavePolicySerializer
    permission_classes = [IsAdminOrManagerOnly]


class PublicHolidayViewSet(viewsets.ModelViewSet):
    queryset = PublicHoliday.objects.all()
    serializer_class = PublicHolidaySerializer
    permission_classes = [IsAdminOrManagerOnly]


class EmployeeBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmployeeBalanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if _is_leave_admin(user):
            return EmployeeBalance.objects.all()
        if _user_in_groups(user, [ROLE_LINE_MANAGER]):
            employee_ids = _managed_employee_ids(user)
            if employee_ids:
                return EmployeeBalance.objects.filter(employee_id__in=employee_ids)
        if hasattr(user, "employee"):
            return EmployeeBalance.objects.filter(employee=user.employee)
        return EmployeeBalance.objects.none()


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if _is_leave_admin(user):
            return LeaveRequest.objects.all()
        if _user_in_groups(user, [ROLE_LINE_MANAGER]):
            employee_ids = _managed_employee_ids(user)
            if employee_ids:
                return LeaveRequest.objects.filter(employee_id__in=employee_ids)
        if hasattr(user, "employee"):
            return LeaveRequest.objects.filter(employee=user.employee)
        return LeaveRequest.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, "employee"):
            inst = serializer.save(employee=self.request.user.employee)
            with contextlib.suppress(Exception):
                message = (
                    f"Leave requested: {inst.employee_id} "
                    f"{inst.start_date}→{inst.end_date}"
                )
                log_action(
                    "leave_request_created",
                    actor=self.request.user,
                    message=message,
                    model_name="LeaveRequest",
                    record_id=getattr(inst, "pk", None),
                    ip_address=self.request.META.get("REMOTE_ADDR", "") or "",
                )
        else:
            raise ValidationError(
                {"detail": "User does not have an associated Employee profile."}
            )

    def perform_update(self, serializer):
        inst = self.get_object()
        prev_status = getattr(inst, "status", None)
        updated = serializer.save()
        new_status = getattr(updated, "status", None)
        if prev_status != new_status:
            with contextlib.suppress(Exception):
                message = f"Leave status changed: {prev_status}→{new_status}"
                log_action(
                    "leave_status_changed",
                    actor=self.request.user,
                    message=message,
                    model_name="LeaveRequest",
                    record_id=getattr(updated, "pk", None),
                    before={"status": prev_status},
                    after={"status": new_status},
                    ip_address=self.request.META.get("REMOTE_ADDR", "") or "",
                )


class BalanceHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BalanceHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if _is_leave_admin(user):
            return BalanceHistory.objects.all()
        if _user_in_groups(user, [ROLE_LINE_MANAGER]):
            employee_ids = _managed_employee_ids(user)
            if employee_ids:
                return BalanceHistory.objects.filter(employee_id__in=employee_ids)
        if hasattr(user, "employee"):
            return BalanceHistory.objects.filter(employee=user.employee)
        return BalanceHistory.objects.none()
