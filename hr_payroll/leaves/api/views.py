"""Leaves API endpoints and helpers."""

import contextlib
import logging
from datetime import date

from django.http import QueryDict
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
from hr_payroll.leaves.api.serializers import LeaveRequestSerializer
from hr_payroll.leaves.api.serializers import LeaveTypeSerializer
from hr_payroll.leaves.api.serializers import PublicHolidaySerializer
from hr_payroll.leaves.models import BalanceHistory
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday

logger = logging.getLogger(__name__)


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


# App-level LeavePolicy endpoints are deprecated. Policies are managed globally
# via OrganizationPolicies endpoints (see config.api_router orgs/.../policies).


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

    def _normalize_frontend_payload(self, data: dict) -> dict:  # noqa: C901
        """Accept flexible frontend keys and map to serializer fields.

        Supported aliases:
        - leave type: `type` | `leaveType` | `leave_type` → resolve default policy
        - dates: `startDate` → `start_date`, `endDate` → `end_date`
        - duration: `days` → `duration`
        - notes: `reason` → `notes`
        - on-behalf requests (optional): `employee_id` passthrough (used below)
        """
        # Flatten QueryDict (form/multipart) to simple dict with scalar values
        out = data.dict() if isinstance(data, QueryDict) else dict(data)

        if "startDate" in out and "start_date" not in out:
            out["start_date"] = out.pop("startDate")
        if "endDate" in out and "end_date" not in out:
            out["end_date"] = out.pop("endDate")
        if "days" in out and "duration" not in out:
            out["duration"] = out.pop("days")
        if "reason" in out and "notes" not in out:
            out["notes"] = out.pop("reason")

        # Resolve policy from leave type aliases if policy not provided
        if not out.get("policy"):
            type_value = (
                out.get("type") or out.get("leaveType") or out.get("leave_type")
            )
            if type_value:
                # Resolve LeaveType by case-insensitive name
                lt = LeaveType.objects.filter(
                    name__iexact=str(type_value).strip()
                ).first()
                if lt is None:
                    # Fallback: try title case (Annual → Annual), else leave unresolved
                    lt = LeaveType.objects.filter(
                        name__iexact=str(type_value).title()
                    ).first()
                if lt is None:
                    raise ValidationError({"type": "Unknown leave type"})

                policy = (
                    LeavePolicy.objects.filter(
                        leave_type=lt, name=f"Global: {lt.name}"
                    ).first()
                    or LeavePolicy.objects.filter(leave_type=lt, is_active=True)
                    .order_by("-id")
                    .first()
                )  # Prefer default global policy for this type
                if not policy:
                    raise ValidationError(
                        {"policy": "No policy configured for this leave type"}
                    )
                out["policy"] = policy.id

        # Auto-compute duration if missing and both dates provided
        if not out.get("duration") and out.get("start_date") and out.get("end_date"):
            try:
                sd = date.fromisoformat(str(out["start_date"]))
                ed = date.fromisoformat(str(out["end_date"]))
                if ed < sd:
                    raise ValidationError(
                        {"end_date": "End date cannot be before start date"}
                    )
                out["duration"] = (ed - sd).days + 1
            except ValueError:
                # Let serializer/validator handle bad dates
                pass

        return out

    def perform_create(self, serializer):
        # Allow HR/Managers to create on-behalf requests using `employee_id`
        target_employee = getattr(self.request.user, "employee", None)
        employee_id = self.request.data.get("employee_id")
        if employee_id:
            try:
                target_employee = Employee.objects.get(pk=int(employee_id))
            except Employee.DoesNotExist as exc:  # pragma: no cover - simple validation
                raise ValidationError({"employee_id": "Employee not found"}) from exc

        if target_employee is not None:
            inst = serializer.save(employee=target_employee)
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

    def create(self, request, *args, **kwargs):
        # Accept flexible frontend payload and normalize before validation
        payload_preview = {}
        for key, value in request.data.items():
            if hasattr(value, "name"):
                payload_preview[key] = f"<File: {getattr(value, 'name', '')}>"
            else:
                payload_preview[key] = value
        logger.info("Incoming leave request payload: %s", payload_preview)

        data = self._normalize_frontend_payload(request.data)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

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
