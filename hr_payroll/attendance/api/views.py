import ipaddress
from collections import defaultdict

from django.conf import settings
from django.db import models
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
from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment
from hr_payroll.attendance.models import OfficeNetwork
from hr_payroll.employees.api.permissions import IsAdminOrHROrLineManagerScopedWrite
from hr_payroll.employees.api.permissions import IsAdminOrManagerOnly
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


def _ensure_aware(dt):
    """Return a timezone-aware datetime from possibly naive input.

    - If dt is None, returns None
    - If dt is naive, make it aware in the current timezone
    - If already aware, return as-is
    """
    if dt is None:
        return None
    if timezone.is_naive(dt):
        try:
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except (ValueError, TypeError):
            return timezone.make_aware(dt)
    return dt


@extend_schema_view(
    list=extend_schema(tags=["Attendance"]),
    retrieve=extend_schema(tags=["Attendance"]),
    create=extend_schema(tags=["Attendance"]),
    update=extend_schema(tags=["Attendance"]),
    partial_update=extend_schema(tags=["Attendance"]),
    destroy=extend_schema(tags=["Attendance"]),
)
class AttendanceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """ViewSet for attendance records.

    Endpoints:
    - list/create/update/destroy attendance
    - POST /{pk}/clock-out/ to set clock_out
    - POST /{pk}/adjust-paid-time/ to adjust paid_time (creates an adjustment record)
    """

    queryset = Attendance.objects.select_related("employee").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrManagerOnly]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAuthenticated()]
        return super().get_permissions()

    @extend_schema(
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
        ]
    )
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
        detail=False,
        methods=["post"],
        url_path="manual-entry",
        serializer_class=ManualEntrySerializer,
    )
    @extend_schema(
        tags=["Attendance"],
        request=ManualEntrySerializer,
        responses=AttendanceSerializer,
        description=(
            "Manual entry: create a record for a specific employee. Admin/Manager only."
        ),
    )
    def manual_entry(self, request):
        u = request.user
        ser = ManualEntrySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        if not (
            getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin", "Manager"])
        ):
            return Response({"detail": "Forbidden"}, status=403)
        employee_id = vd.get("employee") or request.data.get("employee_id")
        if not employee_id:
            return Response({"employee": "required"}, status=400)
        target_emp = Employee.objects.filter(pk=employee_id).first()
        if not target_emp:
            return Response({"detail": "Employee not found"}, status=404)
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
        return Response(self.get_serializer(att).data, status=201)

    @action(
        detail=True,
        methods=["post"],
        url_path="approve",
        permission_classes=[IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite],
    )
    @extend_schema(tags=["Attendance"])
    def approve(self, request, pk=None):
        """Approve an attendance record."""
        inst = self.get_object()
        if inst.status != Attendance.Status.APPROVED:
            inst.status = Attendance.Status.APPROVED
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
        ser = EmployeeClockInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        # Elevated users may clock-in for the specified employee without IP restriction
        elevated = getattr(u, "is_staff", False) or _user_in_groups(
            u, ["Admin", "Manager"]
        )
        target_emp = Employee.objects.filter(pk=employee_id).first()
        if not target_emp:
            return Response({"detail": "Employee not found"}, status=404)
        if not elevated:
            my_emp_id = getattr(getattr(u, "employee", None), "id", None)
            if str(my_emp_id) != str(employee_id):
                return Response({"detail": "Forbidden"}, status=403)
            # IP restriction for self-submission
            xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            remote_ip = xff or (request.META.get("REMOTE_ADDR") or "").strip()
            if not _is_ip_allowed(remote_ip):
                return Response(
                    {
                        "detail": (
                            f"Self clock-in allowed only from company network. "
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
        elevated = getattr(u, "is_staff", False) or _user_in_groups(
            u, ["Admin", "Manager"]
        )
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
        inst.status = Attendance.Status.PENDING
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
        """Approve an attendance record (HR/Admin/Line Manager within scope)."""
        inst = self.get_object()
        if inst.status != Attendance.Status.APPROVED:
            inst.status = Attendance.Status.APPROVED
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
        if inst.status != Attendance.Status.PENDING:
            inst.status = Attendance.Status.PENDING
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
