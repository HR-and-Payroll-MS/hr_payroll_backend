import contextlib
import datetime as dt
import ipaddress
from collections import defaultdict

from django.conf import settings
from django.db import IntegrityError
from django.db import models
from django.http import QueryDict
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.dateparse import parse_duration
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.attendance.api.serializers import AttendanceAdjustmentSerializer
from hr_payroll.attendance.api.serializers import AttendanceCorrectionSerializer
from hr_payroll.attendance.api.serializers import AttendanceSerializer
from hr_payroll.attendance.api.serializers import DepartmentAttendanceSummarySerializer
from hr_payroll.attendance.api.serializers import (
    DepartmentEmployeeAttendanceRowSerializer,
)
from hr_payroll.attendance.api.serializers import EmployeeClockInSerializer
from hr_payroll.attendance.api.serializers import FingerprintScanSerializer
from hr_payroll.attendance.api.serializers import ManualEntrySerializer
from hr_payroll.attendance.api.serializers import SelfAttendanceActionSerializer
from hr_payroll.attendance.api.serializers import SelfAttendanceQuerySerializer
from hr_payroll.attendance.api.serializers import SelfClockOutSerializer
from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment
from hr_payroll.attendance.models import OfficeNetwork
from hr_payroll.audit.utils import log_action
from hr_payroll.employees.api.permissions import ROLE_LINE_MANAGER
from hr_payroll.employees.api.permissions import IsAdminOrHROrLineManagerScopedWrite
from hr_payroll.employees.api.permissions import IsAdminOrManagerOnly
from hr_payroll.employees.api.permissions import _line_manager_in_scope
from hr_payroll.employees.api.permissions import _user_in_groups
from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department
from hr_payroll.policies import attendance_edit_window_days
from hr_payroll.policies import get_policy_document

MIN_SELF_CLOCK_OUT_HOURS = 0
_EXCLUDED_DOCKER_SUBNETS = []
for _cidr in getattr(
    settings,
    "OFFICE_NETWORK_EXCLUDE_CIDRS",
    ["172.17.0.0/16", "172.18.0.0/16", "172.19.0.0/16"],
):
    try:
        _EXCLUDED_DOCKER_SUBNETS.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        continue


class IsAdminManagerOrLineManagerOnly(BasePermission):
    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return False
        if getattr(u, "is_staff", False):
            return True
        return _user_in_groups(u, ["Admin", "Manager", ROLE_LINE_MANAGER])


def _is_ip_allowed(remote_ip: str) -> bool:
    """Return True if remote_ip is within any active OfficeNetwork CIDR."""
    # If no office networks are configured, deny by default (policy enforcement).
    if not OfficeNetwork.objects.filter(is_active=True).exists():
        return False
    if not remote_ip:
        return False
    try:
        addr = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False
    for excluded in _EXCLUDED_DOCKER_SUBNETS:
        if addr in excluded:
            return False
    for net in OfficeNetwork.objects.filter(is_active=True).only("cidr"):
        try:
            network = ipaddress.ip_network(net.cidr, strict=False)
        except ValueError:
            continue
        if addr in network:
            return True
    return False


def _get_remote_ip(request) -> str | None:
    """Best-effort remote client IP extraction.

    Prefers `X-Forwarded-For` (first hop) when present, otherwise falls back to
    `REMOTE_ADDR`.
    """
    meta = getattr(request, "META", {}) or {}
    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # XFF format: client, proxy1, proxy2
        first = str(xff).split(",")[0].strip()
        return first or None
    real_ip = meta.get("HTTP_X_REAL_IP")
    if real_ip:
        return str(real_ip).strip() or None
    ra = meta.get("REMOTE_ADDR")
    return str(ra).strip() if ra else None


def _ensure_aware(value):
    """Normalize datetimes, tolerating isoformat strings and naive values."""
    if value is None:
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _is_elevated_user(user) -> bool:
    """Return True for staff/Admin/Manager roles used to bypass self scope."""
    if not (user and getattr(user, "is_authenticated", False)):
        return False
    if getattr(user, "is_staff", False):
        return True
    return _user_in_groups(user, ["Admin", "Manager"])


def _resolve_status_from_request(request, default=Attendance.Status.PRESENT):
    """Extract and validate a requested attendance status choice."""
    data = getattr(request, "data", None)
    candidate = None
    if isinstance(data, (QueryDict, dict)):
        candidate = data.get("status")
    if not candidate:
        return default, None
    candidate = str(candidate).upper()
    if candidate not in Attendance.Status.values:
        allowed = ", ".join(Attendance.Status.values)
        return None, Response(
            {"status": f"Invalid status. Use one of: {allowed}."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return candidate, None


@extend_schema_view(
    list=extend_schema(
        tags=["Attendance"],
        parameters=[
            OpenApiParameter(
                name="employee",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Filter by employee ID",
            ),
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Filter by exact date (YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Filter records from this date (inclusive)",
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Filter records up to this date (inclusive)",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                enum=[c for c, _ in Attendance.Status.choices],
                location=OpenApiParameter.QUERY,
                description="Filter by approval status",
            ),
            OpenApiParameter(
                name="location",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter where clock-in/out location contains this text",
            ),
            OpenApiParameter(
                name="office",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by employee office (icontains)",
            ),
            OpenApiParameter(
                name="record_type",
                type=OpenApiTypes.STR,
                enum=["clock", "adjust"],
                location=OpenApiParameter.QUERY,
                description=(
                    "Filter adjustments only (adjust) or clock records (clock)"
                ),
            ),
        ],
    ),
    retrieve=extend_schema(tags=["Attendance"]),
)
class AttendanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    """Top-level attendance endpoints for admin/manager level workflows."""

    queryset = Attendance.objects.select_related("employee", "employee__user").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsAdminManagerOrLineManagerOnly]

    def get_permissions(self):
        # Editing clock-in/out timestamps and locations must be restricted to
        # Admin/Manager (HR) only. Line Managers can view department-scoped
        # lists/reports and approve within scope, but cannot directly alter
        # punch times.
        if getattr(self, "action", None) in {
            "update",
            "partial_update",
            "clock_out",
            "delete_clock_out",
        }:
            return [IsAuthenticated(), IsAdminOrManagerOnly()]
        return super().get_permissions()

    def get_serializer_class(self):
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return AttendanceCorrectionSerializer
        return super().get_serializer_class()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        inst = self.get_object()

        # Some clients clear datetimes by sending an empty string ("") instead of
        # JSON null. DRF's DateTimeField rejects "" before it reaches serializer
        # validation, so normalize here.
        if hasattr(request.data, "copy"):
            data = request.data.copy()
        else:
            data = dict(request.data)

        # Optional UI helper flag: treat as an instruction to clear clock-out.
        delete_flag = data.get("delete_clock_out")
        if isinstance(delete_flag, str):
            delete_flag = delete_flag.strip().lower() in {"1", "true", "yes", "on"}
        if delete_flag is True:
            data["clock_out"] = None
            data.setdefault("clock_out_location", "")
            # Remove to avoid "unknown field" errors.
            data.pop("delete_clock_out", None)

        for dt_field in ["clock_in", "clock_out"]:
            if dt_field in data:
                v = data.get(dt_field)
                if v in {"", "null"}:
                    data[dt_field] = None

        for text_field in ["clock_in_location", "clock_out_location", "notes"]:
            if text_field in data and data.get(text_field) is None:
                data[text_field] = ""

        ser = AttendanceCorrectionSerializer(inst, data=data, partial=partial)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(AttendanceSerializer(inst).data, status=200)

    def get_queryset(self):  # noqa: C901
        qs = super().get_queryset()
        u = getattr(self.request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return qs.none()

        # Line managers are restricted to their own department.
        if _user_in_groups(u, [ROLE_LINE_MANAGER]) and not _is_elevated_user(u):
            my_emp = getattr(u, "employee", None)
            dept_id = getattr(my_emp, "department_id", None)
            if not dept_id:
                return qs.none()
            qs = qs.filter(employee__department_id=dept_id)
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        date = self.request.query_params.get("date")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        status_param = self.request.query_params.get("status")
        location = self.request.query_params.get("location")
        office = self.request.query_params.get("office")
        record_type = self.request.query_params.get("record_type")
        if employee:
            qs = qs.filter(employee_id=employee)
        if date:
            qs = qs.filter(date=date)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        if status_param:
            qs = qs.filter(status=status_param)
        if location:
            qs = qs.filter(
                models.Q(clock_in_location__icontains=location)
                | models.Q(clock_out_location__icontains=location)
            )
        if office:
            qs = qs.filter(employee__office__icontains=office)
        if record_type == "adjust":
            qs = qs.filter(adjustments__isnull=False)
        return qs

    @action(
        detail=True,
        methods=["delete"],
        url_path="clock-out",
        permission_classes=[IsAuthenticated, IsAdminManagerOrLineManagerOnly],
    )
    @extend_schema(tags=["Attendance"], request=None, responses=AttendanceSerializer)
    def delete_clock_out(self, request, pk=None):
        """Clear clock_out fields (does not delete the attendance record)."""

        inst = self.get_object()
        inst.clock_out = None
        inst.clock_out_location = ""
        inst.save(update_fields=["clock_out", "clock_out_location", "updated_at"])
        return Response(AttendanceSerializer(inst).data, status=200)

    @action(detail=True, methods=["post", "delete"], url_path="clock-out")
    @extend_schema(tags=["Attendance"])
    def clock_out(self, request, pk=None):
        """Set clock_out time and optional location."""
        inst = self.get_object()

        if request.method.upper() == "DELETE":
            inst.clock_out = None
            inst.clock_out_location = ""
            inst.save(update_fields=["clock_out", "clock_out_location", "updated_at"])
            return Response(self.get_serializer(inst).data, status=200)

        u = request.user
        groups = getattr(u, "groups", None)
        is_hr = bool(getattr(u, "is_staff", False)) or bool(
            groups and groups.filter(name__in=["Admin", "Manager"]).exists()
        )
        is_line_manager = bool(groups and groups.filter(name="Line Manager").exists())
        if not (is_hr or is_line_manager):
            if getattr(getattr(u, "employee", None), "id", None) != getattr(
                inst, "employee_id", None
            ):
                return Response(
                    {"detail": "Forbidden"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        clock_out = request.data.get("clock_out")
        clock_out_location = request.data.get("clock_out_location")
        notes = request.data.get("notes")
        if not clock_out:
            return Response(
                {"clock_out": "required"}, status=status.HTTP_400_BAD_REQUEST
            )
        dt = parse_datetime(clock_out) if isinstance(clock_out, str) else clock_out
        dt = _ensure_aware(dt)
        if dt is None:
            return Response(
                {"clock_out": "invalid datetime"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inst.clock_out = dt
        if clock_out_location:
            inst.clock_out_location = clock_out_location
        update_fields = ["clock_out", "clock_out_location", "updated_at"]
        if isinstance(notes, str):
            inst.notes = notes
            update_fields.append("notes")
        inst.save(update_fields=update_fields)
        serializer = self.get_serializer(inst)
        return Response(serializer.data)

    # Note: no top-level clock-in; use nested employee endpoints instead.

    def _department_scope_queryset(self, user):
        if _is_elevated_user(user):
            return Department.objects.filter(is_active=True)
        if _user_in_groups(user, [ROLE_LINE_MANAGER]):
            emp = getattr(user, "employee", None)
            dept_id = getattr(emp, "department_id", None)
            if not dept_id:
                return Department.objects.none()
            return Department.objects.filter(is_active=True, pk=dept_id)
        return None

    def _parse_target_date(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return timezone.now().date(), None
        try:
            return dt.date.fromisoformat(str(date_str)), None
        except ValueError:
            return None, Response({"date": "invalid"}, status=400)

    @action(
        detail=False,
        methods=["get"],
        url_path="departments",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(
        tags=["Attendance"],
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
            )
        ],
        responses=DepartmentAttendanceSummarySerializer(many=True),
    )
    def departments_summary(self, request):
        """Return per-department totals for a date (default: today).

        Designed for UI: first show departments with counts (present/absent/permitted).
        """

        dept_qs = self._department_scope_queryset(request.user)
        if dept_qs is None:
            return Response({"detail": "Forbidden"}, status=403)
        target_date, error = self._parse_target_date(request)
        if error:
            return error

        rows: list[dict] = []
        for dept in dept_qs.order_by("name"):
            total_employees = Employee.objects.filter(
                department=dept, is_active=True
            ).count()
            status_counts = {
                r["status"]: int(r["c"])
                for r in Attendance.objects.filter(
                    date=target_date,
                    employee__department=dept,
                    employee__is_active=True,
                )
                .values("status")
                .annotate(c=models.Count("id"))
            }
            attendance_total = sum(status_counts.values())
            present = status_counts.get(Attendance.Status.PRESENT, 0)
            permitted = status_counts.get(Attendance.Status.PERMITTED, 0)
            absent_records = status_counts.get(Attendance.Status.ABSENT, 0)
            no_record = max(total_employees - attendance_total, 0)
            absent = absent_records + no_record

            rows.append(
                {
                    "department_id": dept.id,
                    "department_name": dept.name,
                    "date": target_date,
                    "total_employees": total_employees,
                    "present": present,
                    "absent": absent,
                    "permitted": permitted,
                }
            )

        return Response(DepartmentAttendanceSummarySerializer(rows, many=True).data)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"departments/(?P<department_id>[^/.]+)",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(
        tags=["Attendance"],
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
            )
        ],
        responses=DepartmentEmployeeAttendanceRowSerializer(many=True),
    )
    def department_attendance(self, request, department_id=None):  # noqa: C901, PLR0911, PLR0912
        """Return one row per employee in a department for a date (default: today)."""

        target_date, error = self._parse_target_date(request)
        if error:
            return error

        try:
            dept_id_int = int(department_id)
        except (TypeError, ValueError):
            return Response({"department_id": "invalid"}, status=400)

        dept = Department.objects.filter(pk=dept_id_int, is_active=True).first()
        if not dept:
            return Response({"detail": "Not found"}, status=404)

        if not _is_elevated_user(request.user):
            if not _user_in_groups(request.user, [ROLE_LINE_MANAGER]):
                return Response({"detail": "Forbidden"}, status=403)
            emp = getattr(request.user, "employee", None)
            if not emp or emp.department_id != dept.id:
                return Response({"detail": "Forbidden"}, status=403)

        employees = (
            Employee.objects.select_related("user")
            .filter(department=dept, is_active=True)
            .order_by("user__username")
        )
        attendance_by_employee_id = {
            a.employee_id: a
            for a in Attendance.objects.select_related("employee", "employee__user")
            .filter(date=target_date, employee__in=employees)
            .all()
        }

        # HR users often need to correct days that currently have no Attendance row.
        # The frontend expects an attendance_id to PATCH; when it's null it ends up
        # calling /api/v1/attendances/null/ and gets a 404. To keep the frontend
        # contract stable, auto-create placeholder Attendance rows for missing
        # employees on this date (HR/admin only).
        if _is_elevated_user(request.user):
            missing_employees = [
                e for e in employees if e.id not in attendance_by_employee_id
            ]
            if missing_employees:
                try:
                    created = Attendance.objects.bulk_create(
                        [
                            Attendance(
                                employee=e,
                                date=target_date,
                                clock_in=None,
                                clock_in_location="",
                                clock_out=None,
                                clock_out_location="",
                                status=Attendance.Status.ABSENT,
                                notes="",
                            )
                            for e in missing_employees
                        ],
                        ignore_conflicts=True,
                    )
                except IntegrityError:
                    # This typically means the DB schema is behind the code (e.g.
                    # Attendance.clock_in is still NOT NULL). Returning 409 makes the
                    # root cause obvious and avoids a noisy 500 stack trace.
                    detail = (
                        "Database schema is out of date for attendance placeholders. "
                        "Run migrations."
                    )
                    return Response(
                        {
                            "detail": detail,
                            "code": "DB_SCHEMA_OUT_OF_DATE",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                # Refresh mapping for any newly created rows
                if created or missing_employees:
                    for a in Attendance.objects.filter(
                        date=target_date, employee__in=missing_employees
                    ):
                        attendance_by_employee_id[a.employee_id] = a

        rows: list[dict] = []
        for e in employees:
            u = getattr(e, "user", None)
            name = ""
            if u is not None and hasattr(u, "get_full_name"):
                name = (u.get_full_name() or "").strip()
            if not name and u is not None:
                name = getattr(u, "username", "")
            att = attendance_by_employee_id.get(e.id)
            if att is None:
                rows.append(
                    {
                        "employee_id": e.id,
                        "employee_name": name,
                        "date": target_date,
                        "attendance_id": None,
                        "clock_in": None,
                        "clock_in_location": "",
                        "status": Attendance.Status.ABSENT,
                        "clock_out": None,
                        "clock_out_location": "",
                        "work_schedule_hours": 8,
                        "paid_time": dt.timedelta(0),
                        "notes": "",
                    }
                )
                continue

            rows.append(
                {
                    "employee_id": e.id,
                    "employee_name": name,
                    "date": att.date,
                    "attendance_id": att.id,
                    "clock_in": att.clock_in,
                    "clock_in_location": att.clock_in_location or "",
                    "status": att.status,
                    "clock_out": att.clock_out,
                    "clock_out_location": att.clock_out_location or "",
                    "work_schedule_hours": int(att.work_schedule_hours or 0),
                    "paid_time": att.paid_time or dt.timedelta(0),
                    "notes": att.notes or "",
                }
            )

        return Response(DepartmentEmployeeAttendanceRowSerializer(rows, many=True).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="approve",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance"])
    def approve(self, request, pk=None):
        """Approve an attendance record, optionally overriding status."""
        inst = self.get_object()
        prev_status = getattr(inst, "status", None)
        user = request.user
        if _user_in_groups(user, [ROLE_LINE_MANAGER]) and not _line_manager_in_scope(
            user, inst
        ):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        new_status, error = _resolve_status_from_request(request)
        if error:
            return error
        if inst.status != new_status:
            inst.status = new_status
            inst.save(update_fields=["status", "updated_at"])
        message = (
            f"Attendance approved: employee={inst.employee_id} "
            f"date={inst.date} status={inst.status}"
        )
        with contextlib.suppress(Exception):
            log_action(
                "attendance_approved",
                actor=request.user,
                message=message,
                model_name="Attendance",
                record_id=getattr(inst, "pk", None),
                before={"status": prev_status},
                after={"status": inst.status},
                ip_address=request.META.get("REMOTE_ADDR", "") or "",
            )
        return Response({"status": inst.status})

    @action(
        detail=False,
        methods=["get"],
        url_path="my/summary",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(
        tags=["Attendance Reports"],
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
            ),
        ],
    )
    def my_summary(self, request):
        """Aggregate my attendance for a date range."""
        u = request.user
        emp = getattr(u, "employee", None)
        if not emp:
            return Response({"detail": "No employee profile"}, status=400)
        today = timezone.now().date()
        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")
        start = (
            timezone.datetime.fromisoformat(start_str).date()
            if start_str
            else today.replace(day=1)
        )
        end = timezone.datetime.fromisoformat(end_str).date() if end_str else today
        qs = Attendance.objects.filter(employee=emp, date__gte=start, date__lte=end)
        total_logged = timezone.timedelta(0)
        total_paid = timezone.timedelta(0)
        total_scheduled = timezone.timedelta(0)
        for a in qs:
            if a.clock_out:
                total_logged += a.logged_time or timezone.timedelta(0)
            total_paid += a.paid_time or timezone.timedelta(0)
            total_scheduled += timezone.timedelta(hours=int(a.work_schedule_hours))
        overtime = total_paid - total_scheduled
        deficit = total_scheduled - total_paid

        def fmt(td):
            total_seconds = int(td.total_seconds())
            sign = "+" if total_seconds >= 0 else "-"
            total_seconds = abs(total_seconds)
            hours, rem = divmod(total_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"

        return Response(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "count": qs.count(),
                "total_logged": fmt(total_logged),
                "total_paid": fmt(total_paid),
                "overtime": fmt(overtime),
                "deficit": fmt(deficit),
            }
        )

    # Note: no top-level fingerprint scan; use nested employee endpoints.

    @action(
        detail=True,
        methods=["post"],
        url_path="adjust-paid-time",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance • Records"])
    def adjust_paid_time(self, request, pk=None):  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Adjust paid_time and create an adjustment audit record."""
        inst = self.get_object()
        policy = get_policy_document()
        attendance_policy = (
            policy.get("attendancePolicy", {}) if isinstance(policy, dict) else {}
        )
        overtime_rules = (
            attendance_policy.get("overtimeRules", {})
            if isinstance(attendance_policy, dict)
            else {}
        )
        correction_policy = (
            attendance_policy.get("attendanceCorrection", {})
            if isinstance(attendance_policy, dict)
            else {}
        )

        # Enforce edit window
        window_days = attendance_edit_window_days()
        if (timezone.now().date() - inst.date).days > window_days:
            return Response(
                {"detail": f"Edit window exceeded ({window_days} days)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_paid = request.data.get("paid_time")
        notes = request.data.get("notes", "")

        docs_required = (
            (correction_policy.get("documentationRequired") or {}).get("value")
            if isinstance(correction_policy, dict)
            else None
        )
        if str(docs_required).lower() == "yes" and not str(notes or "").strip():
            return Response(
                {"notes": "required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_paid is None:
            return Response(
                {"paid_time": "required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if isinstance(new_paid, str):
            dur = parse_duration(new_paid)
            if dur is None:
                return Response(
                    {"paid_time": "invalid duration"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_paid = dur
        prev = inst.paid_time
        inst.paid_time = new_paid
        inst.status = Attendance.Status.PERMITTED
        scheduled = timezone.timedelta(hours=int(inst.work_schedule_hours))

        paid = inst.paid_time or timezone.timedelta(0)
        ot_delta = paid - scheduled
        ot_seconds_raw = int(ot_delta.total_seconds())

        # Apply frontend overtime rules (policy-driven) to overtime_seconds.
        overtime_allowed = (
            (overtime_rules.get("overtimeAllowed") or {}).get("value")
            if isinstance(overtime_rules, dict)
            else None
        )
        min_minutes = (
            overtime_rules.get("minMinutes")
            if isinstance(overtime_rules, dict)
            else None
        )
        max_daily_hours = (
            overtime_rules.get("maxDailyHours")
            if isinstance(overtime_rules, dict)
            else None
        )
        max_weekly_hours = (
            overtime_rules.get("maxWeeklyHours")
            if isinstance(overtime_rules, dict)
            else None
        )

        ot_seconds = max(0, ot_seconds_raw)

        if str(overtime_allowed).lower() == "no" and ot_seconds > 0:
            return Response(
                {"detail": "Overtime is not allowed by policy"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            min_seconds = int(min_minutes) * 60 if min_minutes is not None else None
        except (TypeError, ValueError):
            min_seconds = None
        if min_seconds is not None and 0 < ot_seconds < min_seconds:
            ot_seconds = 0

        try:
            max_daily_seconds = (
                int(max_daily_hours) * 3600 if max_daily_hours is not None else None
            )
        except (TypeError, ValueError):
            max_daily_seconds = None
        if max_daily_seconds is not None and ot_seconds > max_daily_seconds:
            ot_seconds = max_daily_seconds

        if max_weekly_hours is not None and ot_seconds > 0:
            try:
                max_weekly_seconds = int(max_weekly_hours) * 3600
            except (TypeError, ValueError):
                max_weekly_seconds = None
            if max_weekly_seconds is not None:
                week_start = inst.date - timezone.timedelta(days=inst.date.weekday())
                week_end = week_start + timezone.timedelta(days=6)
                existing_week_ot = 0
                qs = Attendance.objects.filter(
                    employee=inst.employee,
                    date__gte=week_start,
                    date__lte=week_end,
                ).exclude(pk=inst.pk)
                for row in qs.only("overtime_seconds"):
                    existing_week_ot += max(0, int(row.overtime_seconds or 0))
                if existing_week_ot + ot_seconds > max_weekly_seconds:
                    return Response(
                        {"detail": "Weekly overtime limit exceeded"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        inst.overtime_seconds = ot_seconds
        inst.save(
            update_fields=[
                "paid_time",
                "status",
                "overtime_seconds",
                "updated_at",
            ]
        )
        adj = AttendanceAdjustment.objects.create(
            attendance=inst,
            performed_by=request.user if request.user.is_authenticated else None,
            previous_paid_time=prev,
            new_paid_time=new_paid,
            notes=notes,
        )
        ser = AttendanceAdjustmentSerializer(adj)
        return Response(ser.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=["Employee Attendance"]),
    retrieve=extend_schema(tags=["Employee Attendance"]),
)
class EmployeeAttendanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Nested attendance endpoints scoped by employee id.

    Routes (manual urls in config.urls):
    - GET /api/v1/employees/{employee_id}/attendances/
    - GET /api/v1/employees/{employee_id}/attendances/{pk}/
    - POST /api/v1/employees/{employee_id}/attendances/clock-in/
    - POST /api/v1/employees/{employee_id}/attendances/{pk}/clock-out/
    - POST /api/v1/employees/{employee_id}/attendances/fingerprint/scan/
    """

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Attendance.objects.select_related("employee").all()
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        u = getattr(self.request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return qs.none()
        # Non-elevated must match their own employee id
        if not (
            getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"])
        ):
            my_emp_id = getattr(getattr(u, "employee", None), "id", None)
            if str(my_emp_id) != str(employee_id):
                return qs.none()
        # Allow optional filters similar to top-level for convenience
        date = self.request.query_params.get("date")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        status_param = self.request.query_params.get("status")
        if date:
            qs = qs.filter(date=date)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def _resolve_employee_scope(self, request, employee_id):
        target_emp = Employee.objects.filter(pk=employee_id).first()
        if not target_emp:
            return None, Response({"detail": "Employee not found"}, status=404)
        elevated = _is_elevated_user(request.user)
        if not elevated:
            my_emp_id = getattr(getattr(request.user, "employee", None), "id", None)
            if str(my_emp_id) != str(employee_id):
                return None, Response({"detail": "Forbidden"}, status=403)
        return target_emp, None

    def _resolve_self_employee_scope(self, request, employee_id):
        """Resolve employee and require employee_id to match the authenticated user.

        This prevents URL-tweaking IDOR for punch endpoints (clock-in/out/check).
        """

        my_emp = getattr(getattr(request, "user", None), "employee", None)
        my_emp_id = getattr(my_emp, "id", None)
        if my_emp_id is None:
            return None, Response({"detail": "No employee profile"}, status=400)
        if str(my_emp_id) != str(employee_id):
            return None, Response({"detail": "Forbidden"}, status=403)
        return my_emp, None

    def _scrub_employee_from_payload(self, request):
        payload = request.data
        payload = payload.copy() if hasattr(payload, "copy") else dict(payload)
        with contextlib.suppress(KeyError):
            payload.pop("employee")
        return payload

    def _attendance_payload(self, attendance, target_date):
        punches = []
        if attendance and attendance.clock_in:
            punches.append(
                {
                    "type": "check_in",
                    "time": attendance.clock_in.isoformat(),
                    "location": attendance.clock_in_location or "",
                }
            )
        if attendance and attendance.clock_out:
            punches.append(
                {
                    "type": "check_out",
                    "time": attendance.clock_out.isoformat(),
                    "location": attendance.clock_out_location or "",
                }
            )
        return {
            "date": target_date.isoformat(),
            "attendance_id": getattr(attendance, "pk", None),
            "status": getattr(attendance, "status", None),
            "notes": getattr(attendance, "notes", "") or "",
            "punches": punches,
        }

    def _resolve_self_timestamp(self, data, target_date):
        ts = data.get("timestamp")
        if ts:
            return _ensure_aware(ts)
        time_value = data.get("time")
        if time_value:
            naive = dt.datetime.combine(target_date, time_value)
            return timezone.make_aware(naive, timezone.get_current_timezone())
        return timezone.now()

    @action(
        detail=False,
        methods=["post"],
        url_path="clock-in",
        serializer_class=EmployeeClockInSerializer,
    )
    @extend_schema(
        tags=["Employee Attendance"],
        request=EmployeeClockInSerializer,
        responses=AttendanceSerializer,
    )
    def clock_in(self, request, employee_id=None):
        ser = EmployeeClockInSerializer(data=self._scrub_employee_from_payload(request))
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        # Punch endpoints are always self-only to prevent IDOR via URL tweaking.
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        remote_ip = _get_remote_ip(request)
        if not _is_ip_allowed(remote_ip or ""):
            return Response(
                {
                    "detail": (
                        "Self clock-in allowed only from company network. "
                        f"Detected IP: {remote_ip}"
                    )
                },
                status=403,
            )
        date_val = vd.get("date") or timezone.now().date()
        clock_in_val = vd.get("clock_in")
        clock_in_location = vd["clock_in_location"]

        clock_in_dt = (
            parse_datetime(clock_in_val)
            if isinstance(clock_in_val, str)
            else (clock_in_val or timezone.now())
        )
        clock_in_dt = _ensure_aware(clock_in_dt) or timezone.now()

        existing = Attendance.objects.filter(employee=target_emp, date=date_val).first()
        if existing is not None:
            # Idempotent: if already clocked-in for the date, return the record
            # instead of failing with 400.
            if not existing.clock_in:
                existing.clock_in = clock_in_dt
                existing.clock_in_location = clock_in_location
                # Ensure status flips to PRESENT on first clock-in
                existing.status = Attendance.Status.PRESENT
                existing.save(
                    update_fields=[
                        "clock_in",
                        "clock_in_location",
                        "status",
                        "updated_at",
                    ]
                )
            return Response(AttendanceSerializer(existing).data, status=200)

        att = Attendance.objects.create(
            employee=target_emp,
            date=date_val,
            clock_in=clock_in_dt,
            clock_in_location=clock_in_location,
        )
        return Response(AttendanceSerializer(att).data, status=201)

    @action(
        detail=False,
        methods=["post"],
        url_path="clock-out",
        serializer_class=SelfClockOutSerializer,
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(tags=["Employee Attendance"], request=SelfClockOutSerializer)
    def clock_out_today(self, request, employee_id=None):
        """Clock-out without attendance id.

        Resolves the target attendance by (employee_id, date). This is the
        intended endpoint for frontend punch flows.
        """

        ser = SelfClockOutSerializer(data=self._scrub_employee_from_payload(request))
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error

        target_date = vd.get("date") or timezone.now().date()
        timestamp = self._resolve_self_timestamp(vd, target_date)
        location = vd["location"]
        notes = vd.get("notes", "")

        attendance = Attendance.objects.filter(
            employee=target_emp, date=target_date
        ).first()
        return self._handle_self_check_out(
            attendance, target_date, timestamp, location, notes
        )

    @action(detail=True, methods=["post"], url_path="clock-out")
    @extend_schema(tags=["Employee Attendance"])
    def clock_out(self, request, employee_id=None, pk=None):
        # get_object already filtered by employee_id via queryset
        inst = self.get_object()
        u = request.user
        my_emp_id = getattr(getattr(u, "employee", None), "id", None)
        if str(my_emp_id) != str(employee_id):
            return Response({"detail": "Forbidden"}, status=403)
        clock_out = request.data.get("clock_out")
        clock_out_location = request.data.get("clock_out_location")
        notes = request.data.get("notes")
        if not clock_out:
            return Response({"clock_out": "required"}, status=400)
        clock_out_dt = (
            parse_datetime(clock_out) if isinstance(clock_out, str) else clock_out
        )
        clock_out_dt = _ensure_aware(clock_out_dt)
        if clock_out_dt is None:
            return Response({"clock_out": "invalid datetime"}, status=400)
        if inst.clock_in and (clock_out_dt - inst.clock_in) < dt.timedelta(
            hours=MIN_SELF_CLOCK_OUT_HOURS
        ):
            earliest = inst.clock_in + dt.timedelta(hours=MIN_SELF_CLOCK_OUT_HOURS)
            remaining_seconds = int((earliest - clock_out_dt).total_seconds())
            detail = (
                f"Clock-out not allowed until {MIN_SELF_CLOCK_OUT_HOURS} hours "
                "after clock-in."
            )
            return Response(
                {
                    "detail": detail,
                    "code": "MINIMUM_SHIFT_DURATION_NOT_MET",
                    "min_hours": MIN_SELF_CLOCK_OUT_HOURS,
                    "clock_in": inst.clock_in.isoformat() if inst.clock_in else None,
                    "earliest_clock_out": earliest.isoformat(),
                    "remaining_seconds": max(0, remaining_seconds),
                },
                status=400,
            )
        inst.clock_out = clock_out_dt
        if clock_out_location:
            inst.clock_out_location = clock_out_location
        update_fields = ["clock_out", "clock_out_location", "updated_at"]
        if isinstance(notes, str):
            inst.notes = notes
            update_fields.append("notes")
        inst.save(update_fields=update_fields)
        return Response(AttendanceSerializer(inst).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="fingerprint/scan",
        serializer_class=FingerprintScanSerializer,
    )
    @extend_schema(
        tags=["Employee Attendance"],
        request=FingerprintScanSerializer,
        responses=AttendanceSerializer,
        description=(
            "Fingerprint scan via device token. Creates clock-in if absent, or "
            "closes open record for the day."
        ),
    )
    def fingerprint_scan(self, request, employee_id=None):
        ser = FingerprintScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        token = vd.get("fingerprint_token")
        if not token:
            return Response({"fingerprint_token": "required"}, status=400)
        try:
            emp = Employee.objects.get(fingerprint_token=token)
        except Employee.DoesNotExist:
            return Response({"detail": "Unknown fingerprint token"}, status=404)
        # Ensure token corresponds to path employee_id
        if str(getattr(emp, "id", None)) != str(employee_id):
            return Response({"detail": "Token does not match employee"}, status=400)
        ts_val = vd.get("timestamp") or request.query_params.get("timestamp")
        dt = (
            parse_datetime(ts_val)
            if isinstance(ts_val, str)
            else (ts_val or timezone.now())
        )
        dt = _ensure_aware(dt)
        if dt is None:
            return Response({"timestamp": "invalid datetime"}, status=400)
        date_val = dt.date()
        loc = vd.get("location") or ""

        att = Attendance.objects.filter(employee=emp, date=date_val).first()
        action_taken = None
        if not att:
            att = Attendance.objects.create(
                employee=emp,
                date=date_val,
                clock_in=dt,
                clock_in_location=loc,
            )
            action_taken = "clock_in"
        # If placeholder exists without clock-in, treat as clock-in
        elif not att.clock_in:
            att.clock_in = dt
            if loc:
                att.clock_in_location = loc
            att.status = Attendance.Status.PRESENT
            att.save(
                update_fields=[
                    "clock_in",
                    "clock_in_location",
                    "status",
                    "updated_at",
                ]
            )
            action_taken = "clock_in"
        else:
            if att.clock_out:
                return Response(
                    {"detail": "Attendance already completed for date"},
                    status=400,
                )
            att.clock_out = dt
            if loc:
                att.clock_out_location = loc
            att.save(update_fields=["clock_out", "clock_out_location", "updated_at"])
            action_taken = "clock_out"

        data = AttendanceSerializer(att).data
        data["action"] = action_taken
        return Response(data, status=200 if action_taken == "clock_out" else 201)

    @action(
        detail=False,
        methods=["get"],
        url_path="network-status",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(
        tags=["Employee Attendance"],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "is_office_network": {"type": "boolean"},
                    "ip": {"type": "string"},
                },
            }
        },
        description="Check whether the employee is on an allowed office network.",
    )
    def network_status(self, request, employee_id=None):
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        remote_ip = _get_remote_ip(request)
        return Response(
            {
                "employee": target_emp.pk,
                "is_office_network": _is_ip_allowed(remote_ip or ""),
                "ip": remote_ip,
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="manual-entry",
        serializer_class=ManualEntrySerializer,
    )
    @extend_schema(
        tags=["Employee Attendance"],
        request=ManualEntrySerializer,
        responses=AttendanceSerializer,
        description=(
            "Manual entry: create a record for the targeted employee."
            " Non-admins are limited to their own employee id."
        ),
    )
    def manual_entry(self, request, employee_id=None):
        ser = ManualEntrySerializer(data=self._scrub_employee_from_payload(request))
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        date_str = vd.get("date")
        clock_in_val = vd.get("clock_in")
        clock_in_location = vd.get("clock_in_location")
        notes = vd.get("notes")
        if not clock_in_location:
            return Response({"clock_in_location": "required"}, status=400)
        date_val = (
            timezone.datetime.fromisoformat(str(date_str)).date()
            if date_str
            else timezone.now().date()
        )
        if Attendance.objects.filter(employee=target_emp, date=date_val).exists():
            return Response(
                {"detail": "Attendance already exists for date"}, status=400
            )
        dt = (
            parse_datetime(clock_in_val)
            if isinstance(clock_in_val, str)
            else (clock_in_val or timezone.now())
        )
        dt = _ensure_aware(dt)
        att = Attendance.objects.create(
            employee=target_emp,
            date=date_val,
            clock_in=dt,
            clock_in_location=clock_in_location,
            notes=notes or "",
        )
        return Response(AttendanceSerializer(att).data, status=201)

    @action(
        detail=False,
        methods=["get"],
        url_path="actions",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(tags=["Employee Attendance"], request=None)
    def actions(self, request, employee_id=None):
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        base = f"/api/v1/employees/{employee_id}/attendances"
        return Response(
            {
                "employee": target_emp.pk,
                "base": base,
                "actions": [
                    {"name": "today", "method": "GET", "url": f"{base}/today/"},
                    {"name": "check", "method": "POST", "url": f"{base}/check/"},
                    {"name": "clock_in", "method": "POST", "url": f"{base}/clock-in/"},
                    {
                        "name": "manual_entry",
                        "method": "POST",
                        "url": f"{base}/manual-entry/",
                    },
                    {
                        "name": "fingerprint_scan",
                        "method": "POST",
                        "url": f"{base}/fingerprint/scan/",
                    },
                    {
                        "name": "network_status",
                        "method": "GET",
                        "url": f"{base}/network-status/",
                    },
                    {
                        "name": "clock_out",
                        "method": "POST",
                        "url": f"{base}/<attendance_id>/clock-out/",
                    },
                ],
            }
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="today",
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(tags=["Employee Attendance"], request=None)
    def today(self, request, employee_id=None):
        ser = SelfAttendanceQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        target_date = ser.validated_data.get("date") or timezone.now().date()
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        attendance = Attendance.objects.filter(
            employee=target_emp, date=target_date
        ).first()
        # If HR cleared clock_in (and possibly clock_out), treat the day as not
        # started yet so clients can clock-in again.
        if attendance is not None and attendance.clock_in is None:
            attendance = None
        return Response(self._attendance_payload(attendance, target_date))

    @action(
        detail=False,
        methods=["post"],
        url_path="check",
        serializer_class=SelfAttendanceActionSerializer,
        permission_classes=[IsAuthenticated],
    )
    @extend_schema(tags=["Employee Attendance"], request=SelfAttendanceActionSerializer)
    def check(self, request, employee_id=None):
        ser = SelfAttendanceActionSerializer(
            data=self._scrub_employee_from_payload(request)
        )
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        target_emp, error = self._resolve_self_employee_scope(request, employee_id)
        if error:
            return error
        target_date = vd.get("date") or timezone.now().date()
        timestamp = self._resolve_self_timestamp(vd, target_date)
        location = vd["location"]
        notes = vd.get("notes", "")
        attendance = Attendance.objects.filter(
            employee=target_emp, date=target_date
        ).first()
        if vd["action"] == "check_in":
            return self._handle_self_check_in(
                request,
                target_emp,
                attendance,
                vd,
                target_date,
            )
        return self._handle_self_check_out(
            attendance, target_date, timestamp, location, notes
        )

    def _handle_self_check_in(
        self,
        request,
        employee,
        attendance,
        data,
        target_date,
    ):
        if attendance and attendance.clock_in:
            # Idempotent behavior: if the user is already clocked in for the day,
            # return the current payload instead of failing.
            return Response(
                self._attendance_payload(attendance, target_date), status=200
            )
        remote_ip = _get_remote_ip(request)
        if not _is_ip_allowed(remote_ip or ""):
            return Response(
                {
                    "detail": (
                        "Self clock-in allowed only from company network. "
                        f"Detected IP: {remote_ip or 'unknown'}"
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if attendance and attendance.clock_in is None:
            attendance.clock_in = self._resolve_self_timestamp(data, target_date)
            attendance.clock_in_location = data["location"]
            attendance.notes = data.get("notes", "")
            # Ensure any stale clock-out is cleared as well.
            attendance.clock_out = None
            attendance.clock_out_location = ""
            attendance.save(
                update_fields=[
                    "clock_in",
                    "clock_in_location",
                    "notes",
                    "clock_out",
                    "clock_out_location",
                    "updated_at",
                ]
            )
        else:
            attendance = Attendance.objects.create(
                employee=employee,
                date=target_date,
                clock_in=self._resolve_self_timestamp(data, target_date),
                clock_in_location=data["location"],
                notes=data.get("notes", ""),
            )
        return Response(
            self._attendance_payload(attendance, target_date),
            status=status.HTTP_201_CREATED,
        )

    def _handle_self_check_out(
        self, attendance, target_date, timestamp, location, notes
    ):
        if not attendance or not attendance.clock_in:
            return Response(
                {"detail": "No open attendance record for date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if attendance.clock_out:
            # Idempotent behavior: repeated clock-out should return the current payload.
            return Response(
                self._attendance_payload(attendance, target_date), status=200
            )
        if timestamp < attendance.clock_in:
            return Response(
                {
                    "detail": "Clock-out cannot be before clock-in.",
                    "time": "Clock-out cannot be before clock-in.",
                    "code": "CLOCK_OUT_BEFORE_CLOCK_IN",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (timestamp - attendance.clock_in) < dt.timedelta(
            hours=MIN_SELF_CLOCK_OUT_HOURS
        ):
            earliest = attendance.clock_in + dt.timedelta(
                hours=MIN_SELF_CLOCK_OUT_HOURS
            )
            remaining_seconds = int((earliest - timestamp).total_seconds())
            detail = (
                f"Clock-out not allowed until {MIN_SELF_CLOCK_OUT_HOURS} hours "
                "after clock-in."
            )
            return Response(
                {
                    "detail": detail,
                    "code": "MINIMUM_SHIFT_DURATION_NOT_MET",
                    "min_hours": MIN_SELF_CLOCK_OUT_HOURS,
                    "clock_in": attendance.clock_in.isoformat()
                    if attendance.clock_in
                    else None,
                    "earliest_clock_out": earliest.isoformat(),
                    "remaining_seconds": max(0, remaining_seconds),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        attendance.clock_out = timestamp
        attendance.clock_out_location = location
        update_fields = ["clock_out", "clock_out_location", "updated_at"]
        if notes:
            attendance.notes = notes
            update_fields.append("notes")
        attendance.save(update_fields=update_fields)
        return Response(self._attendance_payload(attendance, target_date))

    @action(
        detail=True,
        methods=["post"],
        url_path="adjust-paid-time",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance • Records"])
    def adjust_paid_time(self, request, pk=None):  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Adjust paid_time and create an adjustment audit record."""
        inst = self.get_object()
        policy = get_policy_document()
        attendance_policy = (
            policy.get("attendancePolicy", {}) if isinstance(policy, dict) else {}
        )
        overtime_rules = (
            attendance_policy.get("overtimeRules", {})
            if isinstance(attendance_policy, dict)
            else {}
        )
        correction_policy = (
            attendance_policy.get("attendanceCorrection", {})
            if isinstance(attendance_policy, dict)
            else {}
        )

        # Enforce edit window
        window_days = attendance_edit_window_days()
        if (timezone.now().date() - inst.date).days > window_days:
            return Response(
                {"detail": f"Edit window exceeded ({window_days} days)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_paid = request.data.get("paid_time")
        notes = request.data.get("notes", "")

        docs_required = (
            (correction_policy.get("documentationRequired") or {}).get("value")
            if isinstance(correction_policy, dict)
            else None
        )
        if str(docs_required).lower() == "yes" and not str(notes or "").strip():
            return Response(
                {"notes": "required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_paid is None:
            return Response(
                {"paid_time": "required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if isinstance(new_paid, str):
            dur = parse_duration(new_paid)
            if dur is None:
                return Response(
                    {"paid_time": "invalid duration"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_paid = dur
        prev = inst.paid_time
        inst.paid_time = new_paid
        inst.status = Attendance.Status.PERMITTED
        scheduled = timezone.timedelta(hours=int(inst.work_schedule_hours))

        paid = inst.paid_time or timezone.timedelta(0)
        ot_delta = paid - scheduled
        ot_seconds_raw = int(ot_delta.total_seconds())

        # Apply frontend overtime rules (policy-driven) to overtime_seconds.
        overtime_allowed = (
            (overtime_rules.get("overtimeAllowed") or {}).get("value")
            if isinstance(overtime_rules, dict)
            else None
        )
        min_minutes = (
            overtime_rules.get("minMinutes")
            if isinstance(overtime_rules, dict)
            else None
        )
        max_daily_hours = (
            overtime_rules.get("maxDailyHours")
            if isinstance(overtime_rules, dict)
            else None
        )
        max_weekly_hours = (
            overtime_rules.get("maxWeeklyHours")
            if isinstance(overtime_rules, dict)
            else None
        )

        ot_seconds = max(0, ot_seconds_raw)

        if str(overtime_allowed).lower() == "no" and ot_seconds > 0:
            return Response(
                {"detail": "Overtime is not allowed by policy"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            min_seconds = int(min_minutes) * 60 if min_minutes is not None else None
        except (TypeError, ValueError):
            min_seconds = None
        if min_seconds is not None and 0 < ot_seconds < min_seconds:
            ot_seconds = 0

        try:
            max_daily_seconds = (
                int(max_daily_hours) * 3600 if max_daily_hours is not None else None
            )
        except (TypeError, ValueError):
            max_daily_seconds = None
        if max_daily_seconds is not None and ot_seconds > max_daily_seconds:
            ot_seconds = max_daily_seconds

        if max_weekly_hours is not None and ot_seconds > 0:
            try:
                max_weekly_seconds = int(max_weekly_hours) * 3600
            except (TypeError, ValueError):
                max_weekly_seconds = None
            if max_weekly_seconds is not None:
                week_start = inst.date - timezone.timedelta(days=inst.date.weekday())
                week_end = week_start + timezone.timedelta(days=6)
                existing_week_ot = 0
                qs = Attendance.objects.filter(
                    employee=inst.employee,
                    date__gte=week_start,
                    date__lte=week_end,
                ).exclude(pk=inst.pk)
                for row in qs.only("overtime_seconds"):
                    existing_week_ot += max(0, int(row.overtime_seconds or 0))
                if existing_week_ot + ot_seconds > max_weekly_seconds:
                    return Response(
                        {"detail": "Weekly overtime limit exceeded"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        inst.overtime_seconds = ot_seconds
        inst.save(
            update_fields=[
                "paid_time",
                "status",
                "overtime_seconds",
                "updated_at",
            ]
        )
        adj = AttendanceAdjustment.objects.create(
            attendance=inst,
            performed_by=request.user if request.user.is_authenticated else None,
            previous_paid_time=prev,
            new_paid_time=new_paid,
            notes=notes,
        )
        ser = AttendanceAdjustmentSerializer(adj)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path="approve",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance • Records"])
    def approve(self, request, pk=None):
        """Approve an attendance record (optionally overriding status)."""
        inst = self.get_object()
        prev_status = getattr(inst, "status", None)
        new_status, error = _resolve_status_from_request(request)
        if error:
            return error
        if inst.status != new_status:
            inst.status = new_status
            inst.save(update_fields=["status", "updated_at"])
        message = (
            f"Attendance approved: employee={inst.employee_id} "
            f"date={inst.date} status={inst.status}"
        )
        with contextlib.suppress(Exception):
            log_action(
                "attendance_approved",
                actor=request.user,
                message=message,
                model_name="Attendance",
                record_id=getattr(inst, "pk", None),
                before={"status": prev_status},
                after={"status": inst.status},
                ip_address=request.META.get("REMOTE_ADDR", "") or "",
            )
        return Response({"status": inst.status})

    @action(
        detail=True,
        methods=["post"],
        url_path="revoke-approval",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance • Records"])
    def revoke_approval(self, request, pk=None):
        """Revoke approval and set back to PENDING."""
        inst = self.get_object()
        if inst.status != Attendance.Status.PERMITTED:
            inst.status = Attendance.Status.PERMITTED
            inst.save(update_fields=["status", "updated_at"])
        return Response({"status": inst.status})

    @action(detail=False, methods=["get"], url_path="my/summary")
    @extend_schema(
        tags=["Attendance Reports"],
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="From date inclusive (default: first day of current month)",
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="To date inclusive (default: today)",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                enum=[c for c, _ in Attendance.Status.choices],
                location=OpenApiParameter.QUERY,
                description="Filter by approval status",
            ),
        ],
    )
    def my_summary(self, request):
        """Aggregate my attendance for a date range: logged, paid, overtime/deficit."""
        u = request.user
        emp = getattr(u, "employee", None)
        if not emp:
            return Response({"detail": "No employee profile"}, status=400)
        today = timezone.now().date()
        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")
        if start_str:
            start = timezone.datetime.fromisoformat(start_str).date()
        else:
            start = today.replace(day=1)
        end = timezone.datetime.fromisoformat(end_str).date() if end_str else today
        status_param = request.query_params.get("status")
        qs = Attendance.objects.filter(employee=emp, date__gte=start, date__lte=end)
        if status_param:
            qs = qs.filter(status=status_param)
        total_logged = timezone.timedelta(0)
        total_paid = timezone.timedelta(0)
        total_scheduled = timezone.timedelta(0)
        for a in qs:
            if a.clock_out:
                total_logged += a.logged_time or timezone.timedelta(0)
            total_paid += a.paid_time or timezone.timedelta(0)
            total_scheduled += timezone.timedelta(hours=int(a.work_schedule_hours))
        overtime = total_paid - total_scheduled
        deficit = total_scheduled - total_paid

        def fmt(td):
            total_seconds = int(td.total_seconds())
            sign = "+" if total_seconds >= 0 else "-"
            total_seconds = abs(total_seconds)
            hours, rem = divmod(total_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"

        return Response(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "count": qs.count(),
                "total_logged": fmt(total_logged),
                "total_paid": fmt(total_paid),
                "overtime": fmt(overtime),
                "deficit": fmt(deficit),
            }
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="team/summary",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(
        tags=["Attendance Reports"],
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="From date inclusive (default: first day of current month)",
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="To date inclusive (default: today)",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                enum=[c for c, _ in Attendance.Status.choices],
                location=OpenApiParameter.QUERY,
                description="Filter by approval status",
            ),
            OpenApiParameter(
                name="office",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by employee office (icontains)",
            ),
        ],
    )
    def team_summary(self, request):
        """Aggregate team attendance.

        Line Manager: direct reports. HR/Admin: all employees. Optional office filter.
        """
        u = request.user
        emp = getattr(u, "employee", None)
        today = timezone.now().date()
        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")
        start = (
            timezone.datetime.fromisoformat(start_str).date()
            if start_str
            else today.replace(day=1)
        )
        end = timezone.datetime.fromisoformat(end_str).date() if end_str else today
        status_param = request.query_params.get("status")
        office = request.query_params.get("office")

        is_hr = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )
        emp_ids = []
        if is_hr:
            qs_emp = Employee.objects.all()
            if office:
                qs_emp = qs_emp.filter(office__icontains=office)
            emp_ids = list(qs_emp.values_list("id", flat=True))
        else:
            if not emp:
                return Response({"detail": "No employee profile"}, status=400)
            qs_emp = emp.managed_employees.all()
            if office:
                qs_emp = qs_emp.filter(office__icontains=office)
            emp_ids = list(qs_emp.values_list("id", flat=True))

        qs = Attendance.objects.filter(
            employee_id__in=emp_ids, date__gte=start, date__lte=end
        )
        if status_param:
            qs = qs.filter(status=status_param)

        totals = defaultdict(
            lambda: {
                "count": 0,
                "total_logged": timezone.timedelta(0),
                "total_paid": timezone.timedelta(0),
                "total_scheduled": timezone.timedelta(0),
            }
        )
        for a in qs.select_related("employee", "employee__user"):
            t = totals[a.employee_id]
            t["count"] += 1
            if a.clock_out:
                t["total_logged"] += a.logged_time or timezone.timedelta(0)
            t["total_paid"] += a.paid_time or timezone.timedelta(0)
            t["total_scheduled"] += timezone.timedelta(hours=int(a.work_schedule_hours))

        def fmt(td):
            total_seconds = int(td.total_seconds())
            sign = "+" if total_seconds >= 0 else "-"
            total_seconds = abs(total_seconds)
            hours, rem = divmod(total_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"

        items = []
        emp_map = {
            e.id: e
            for e in Employee.objects.filter(id__in=emp_ids).select_related("user")
        }
        for emp_id, t in totals.items():
            emp_obj = emp_map.get(emp_id)
            ov = t["total_paid"] - t["total_scheduled"]
            items.append(
                {
                    "employee": str(emp_id),
                    "employee_name": getattr(
                        getattr(emp_obj, "user", None), "name", ""
                    ),
                    "count": t["count"],
                    "total_logged": fmt(t["total_logged"]),
                    "total_paid": fmt(t["total_paid"]),
                    "overtime": fmt(ov),
                    "deficit": fmt(-ov),
                }
            )

        return Response(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "employees": items,
            }
        )
