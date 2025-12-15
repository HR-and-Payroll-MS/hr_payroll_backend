import contextlib
import datetime as dt
import ipaddress
from collections import defaultdict

from django.conf import settings
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
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.attendance.api.serializers import AttendanceAdjustmentSerializer
from hr_payroll.attendance.api.serializers import AttendanceSerializer
from hr_payroll.attendance.api.serializers import EmployeeClockInSerializer
from hr_payroll.attendance.api.serializers import FingerprintScanSerializer
from hr_payroll.attendance.api.serializers import ManualEntrySerializer
from hr_payroll.attendance.api.serializers import SelfAttendanceActionSerializer
from hr_payroll.attendance.api.serializers import SelfAttendanceQuerySerializer
from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment
from hr_payroll.attendance.models import OfficeNetwork
from hr_payroll.employees.api.permissions import ROLE_LINE_MANAGER
from hr_payroll.employees.api.permissions import IsAdminOrHROrLineManagerScopedWrite
from hr_payroll.employees.api.permissions import IsAdminOrManagerOnly
from hr_payroll.employees.api.permissions import _line_manager_in_scope
from hr_payroll.employees.api.permissions import _user_in_groups
from hr_payroll.employees.models import Employee


def _is_ip_allowed(remote_ip: str) -> bool:
    """Return True if remote_ip is within any active OfficeNetwork CIDR."""
    if not remote_ip:
        return False
    try:
        addr = ipaddress.ip_address(remote_ip)
    except ValueError:
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
    """Best-effort extraction of the caller IP address from request META."""
    meta = getattr(request, "META", {}) or {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return meta.get("REMOTE_ADDR")


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
    GenericViewSet,
):
    """Top-level attendance endpoints for admin/manager level workflows."""

    queryset = Attendance.objects.select_related("employee", "employee__user").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrManagerOnly]

    def get_queryset(self):  # noqa: C901
        qs = super().get_queryset()
        u = getattr(self.request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            groups = getattr(u, "groups", None)
            is_hr = bool(getattr(u, "is_staff", False)) or bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            is_lm = bool(groups and groups.filter(name="Line Manager").exists())
            if not (is_hr or is_lm):
                emp = getattr(u, "employee", None)
                if not emp:
                    return qs.none()
                qs = qs.filter(employee=emp)
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

    @action(detail=True, methods=["post"], url_path="clock-out")
    @extend_schema(tags=["Attendance"])
    def clock_out(self, request, pk=None):
        """Set clock_out time and optional location."""
        inst = self.get_object()
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
        u = request.user
        ser = EmployeeClockInSerializer(data=self._scrub_employee_from_payload(request))
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        # Elevated users may clock-in for the specified employee without IP restriction
        target_emp, error = self._resolve_employee_scope(request, employee_id)
        if error:
            return error
        elevated = _is_elevated_user(u)
        if not elevated:
            remote_ip = _get_remote_ip(request)
            if not _is_ip_allowed(remote_ip):
                return Response(
                    {
                        "detail": (
                            "Self clock-in allowed only from company network. "
                            f"Detected IP: {remote_ip}"
                        )
                    },
                    status=403,
                )
        date_str = vd.get("date")
        clock_in_val = vd.get("clock_in")
        clock_in_location = vd.get("clock_in_location")
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
        att = Attendance.objects.create(
            employee=target_emp,
            date=date_val,
            clock_in=dt,
            clock_in_location=clock_in_location,
        )
        return Response(AttendanceSerializer(att).data, status=201)

    @action(detail=True, methods=["post"], url_path="clock-out")
    @extend_schema(tags=["Employee Attendance"])
    def clock_out(self, request, employee_id=None, pk=None):
        # get_object already filtered by employee_id via queryset
        inst = self.get_object()
        u = request.user
        elevated = _is_elevated_user(u)
        if not elevated:
            my_emp_id = getattr(getattr(u, "employee", None), "id", None)
            if str(my_emp_id) != str(employee_id):
                return Response({"detail": "Forbidden"}, status=403)
        clock_out = request.data.get("clock_out")
        clock_out_location = request.data.get("clock_out_location")
        notes = request.data.get("notes")
        if not clock_out:
            return Response({"clock_out": "required"}, status=400)
        dt = parse_datetime(clock_out) if isinstance(clock_out, str) else clock_out
        dt = _ensure_aware(dt)
        if dt is None:
            return Response({"clock_out": "invalid datetime"}, status=400)
        inst.clock_out = dt
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
        target_emp, error = self._resolve_employee_scope(request, employee_id)
        if error:
            return error
        remote_ip = _get_remote_ip(request)
        return Response(
            {
                "employee": target_emp.pk,
                "is_office_network": _is_ip_allowed(remote_ip),
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
        target_emp, error = self._resolve_employee_scope(request, employee_id)
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
        target_emp, error = self._resolve_employee_scope(request, employee_id)
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
        target_date = ser.validated_data.get("date") or timezone.localdate()
        target_emp, error = self._resolve_employee_scope(request, employee_id)
        if error:
            return error
        attendance = Attendance.objects.filter(
            employee=target_emp, date=target_date
        ).first()
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
        target_emp, error = self._resolve_employee_scope(request, employee_id)
        if error:
            return error
        target_date = vd.get("date") or timezone.localdate()
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
        if attendance:
            return Response(
                {"detail": "Attendance already exists for date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _is_elevated_user(request.user):
            remote_ip = _get_remote_ip(request)
            if not _is_ip_allowed(remote_ip):
                return Response(
                    {
                        "detail": (
                            "Self clock-in allowed only from company network. "
                            f"Detected IP: {remote_ip or 'unknown'}"
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
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
            return Response(
                {"detail": "Attendance already has a clock-out."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if timestamp < attendance.clock_in:
            return Response(
                {"time": "Clock-out cannot be before clock-in."},
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
    def adjust_paid_time(self, request, pk=None):
        """Adjust paid_time and create an adjustment audit record."""
        inst = self.get_object()
        # Enforce edit window
        window_days = int(getattr(settings, "ATTENDANCE_EDIT_WINDOW_DAYS", 31))
        if (timezone.now().date() - inst.date).days > window_days:
            return Response(
                {"detail": f"Edit window exceeded ({window_days} days)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_paid = request.data.get("paid_time")
        notes = request.data.get("notes", "")
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
        ot = (inst.paid_time or timezone.timedelta(0)) - scheduled
        inst.overtime_seconds = int(ot.total_seconds())
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
        new_status, error = _resolve_status_from_request(request)
        if error:
            return error
        if inst.status != new_status:
            inst.status = new_status
            inst.save(update_fields=["status", "updated_at"])
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
