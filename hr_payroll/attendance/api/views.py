from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from hr_payroll.attendance.api.serializers import AttendancePunchSerializer
from hr_payroll.attendance.api.serializers import AttendanceRecordSerializer
from hr_payroll.attendance.models import AttendancePunch
from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.attendance.models import OfficeNetworkRange
from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department
from hr_payroll.policies import accessors as policy_accessors


def _client_ip(request) -> str:
    # Prefer explicitly forwarded client IPs in dev; fallback to REMOTE_ADDR (likely docker bridge)
    x_client = request.headers.get("x-client-ip")
    if settings.DEBUG and x_client:
        return x_client.split(",")[0].strip()

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()

    x_real = request.headers.get("x-real-ip")
    if x_real:
        return x_real.strip()

    return request.META.get("REMOTE_ADDR", "")


def _ensure_employee_access(request, employee: Employee) -> None:
    if request.user.is_superuser or request.user.is_staff:
        return
    if getattr(request.user, "employee_id", None) == employee.id:
        return
    # Check if the user is the line manager of the employee
    if (
        hasattr(request.user, "employee")
        and employee.line_manager == request.user.employee
    ):
        return
    msg = "You do not have access to this employee's attendance."
    raise PermissionDenied(msg)


def _get_employee_or_404(employee_id: int) -> Employee:
    try:
        return Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist as exc:  # pragma: no cover - DRF handles 404
        msg = "Employee not found"
        raise Http404(msg) from exc


def _compute_minutes(start_time, end_time, base_date) -> int:
    if not start_time or not end_time:
        return 0

    start_dt = datetime.combine(base_date, start_time)
    end_dt = datetime.combine(base_date, end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return int((end_dt - start_dt).total_seconds() // 60)


def _format_time(value) -> str:
    return value.strftime("%H:%M") if value else ""


def _format_duration(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins:02d}m"


def _ensure_shift_defaults(record: AttendanceRecord) -> None:
    # Always pull current dynamic policy so frontend policy edits take effect immediately.

    # 1. Try to find the shift assigned to this employee
    employee_shift_name = getattr(record.employee, "current_shift", "")
    found_shift = policy_accessors.get_shift_by_name(employee_shift_name)

    if found_shift:
        name, start, end = found_shift
    else:
        # 2. Fallback to global default
        name, start, end = policy_accessors.default_shift()

    changed = False
    if record.shift_name != name:
        record.shift_name = name
        changed = True
    if record.shift_start != start:
        record.shift_start = start
        changed = True
    if record.shift_end != end:
        record.shift_end = end
        changed = True

    schedule_minutes = _compute_minutes(
        record.shift_start, record.shift_end, record.date
    )
    if record.work_schedule_minutes != schedule_minutes:
        record.work_schedule_minutes = schedule_minutes
        changed = True

    if changed:
        record.save(
            update_fields=[
                "shift_name",
                "shift_start",
                "shift_end",
                "work_schedule_minutes",
                "updated_at",
            ]
        )


def _calculate_paid_minutes(record: AttendanceRecord) -> int:
    if record.paid_minutes:
        return record.paid_minutes
    if record.clock_in and record.clock_out:
        return _compute_minutes(record.clock_in, record.clock_out, record.date)
    return 0


def _attendance_status(record: AttendanceRecord) -> str:
    if record.status:
        return record.status.upper()
    if record.clock_in and record.clock_out:
        return "PRESENT"
    if record.clock_in and not record.clock_out:
        return "PRESENT"
    return "ABSENT"


def _build_timestamp(record: AttendanceRecord, value):
    if not value:
        return None
    dt = datetime.combine(record.date, value)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    else:
        dt = dt.astimezone(timezone.get_current_timezone())
    return dt


def _is_late(record: AttendanceRecord) -> bool:
    if not record.clock_in or not record.shift_start:
        return False
    grace = policy_accessors.grace_minutes()
    clock_in_dt = datetime.combine(record.date, record.clock_in)
    shift_start_dt = datetime.combine(record.date, record.shift_start) + timedelta(
        minutes=grace
    )
    return clock_in_dt > shift_start_dt


def _serialize_record(record: AttendanceRecord) -> dict:
    _ensure_shift_defaults(record)

    paid_minutes = _calculate_paid_minutes(record)
    status = _attendance_status(record)

    work_schedule_str = ""
    if record.shift_start and record.shift_end:
        work_schedule_str = (
            f"{_format_time(record.shift_start)} - {_format_time(record.shift_end)}"
        )

    photo = getattr(record.employee, "photo", None)
    photo_url = ""
    if photo:
        try:
            if getattr(photo, "name", ""):
                photo_url = photo.url
        except ValueError:
            photo_url = ""

    return {
        "id": record.id,
        "employee_name": getattr(record.employee.user, "username", ""),
        "employee_pic": photo_url,
        "date": record.date.isoformat(),
        "clock_in": _format_time(record.clock_in),
        "clock_in_location": record.clock_in_location or "",
        "clock_out": _format_time(record.clock_out),
        "clock_out_location": record.clock_out_location or "",
        "status": status,
        "work_schedule_hours": work_schedule_str,
        "paid_time": _format_duration(paid_minutes),
        "paid_minutes": paid_minutes,
        "work_schedule_minutes": record.work_schedule_minutes,
        "notes": record.notes or "",
        "is_late": _is_late(record),
        "is_overtime": bool(
            record.clock_out and paid_minutes > (record.work_schedule_minutes or 0)
        ),
        "attendance_id": record.id,
    }


class NetworkStatusView(APIView):
    """Simple network gate to mirror frontend's /network-status expectation."""

    def get(self, request, employee_id: int):
        employee = _get_employee_or_404(employee_id)
        _ensure_employee_access(request, employee)

        ip = _client_ip(request)
        allowed = False
        matched_range = None
        matched_cidr = None
        for network in OfficeNetworkRange.objects.filter(is_active=True):
            if network.contains(ip):
                allowed = True
                matched_range = network.name
                matched_cidr = network.cidr
                break

        return Response(
            {
                "ip": ip,
                "allowed": allowed,
                "matched_range": matched_range,
                "matched_cidr": matched_cidr,
                "office_name": matched_range,
            }
        )


class TodayAttendanceView(APIView):
    def get(self, request, employee_id: int):
        employee = _get_employee_or_404(employee_id)
        _ensure_employee_access(request, employee)

        today = timezone.localdate()
        record, _ = AttendanceRecord.objects.get_or_create(
            employee=employee,
            date=today,
            defaults={"status": "pending"},
        )
        _ensure_shift_defaults(record)
        data = AttendanceRecordSerializer(record).data
        return Response(data)


class ClockInView(APIView):
    def post(self, request, employee_id: int):
        employee = _get_employee_or_404(employee_id)
        _ensure_employee_access(request, employee)

        now = timezone.localtime()
        record, _ = AttendanceRecord.objects.get_or_create(
            employee=employee,
            date=now.date(),
            defaults={"status": "pending"},
        )
        _ensure_shift_defaults(record)

        if record.clock_in:
            return Response(
                {"detail": "Already clocked in."}, status=status.HTTP_400_BAD_REQUEST
            )

        record.clock_in = now.time()
        record.clock_in_location = request.data.get(
            "clock_in_location", request.data.get("location", "onsite")
        )
        record.status = "present"
        record.save(
            update_fields=["clock_in", "clock_in_location", "status", "updated_at"]
        )

        punch = AttendancePunch.objects.create(
            attendance=record,
            punch_type=AttendancePunch.TYPE_CHECK_IN,
            timestamp=now,
            location=record.clock_in_location,
        )

        return Response(
            {
                "record": AttendanceRecordSerializer(record).data,
                "punch": AttendancePunchSerializer(punch).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ClockOutView(APIView):
    def post(self, request, employee_id: int):
        employee = _get_employee_or_404(employee_id)
        _ensure_employee_access(request, employee)

        now = timezone.localtime()
        try:
            record = AttendanceRecord.objects.get(employee=employee, date=now.date())
        except AttendanceRecord.DoesNotExist:
            return Response(
                {"detail": "No attendance record for today."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if record.clock_out:
            return Response(
                {"detail": "Already clocked out."}, status=status.HTTP_400_BAD_REQUEST
            )

        record.clock_out = now.time()
        record.clock_out_location = request.data.get(
            "clock_out_location", request.data.get("location", "onsite")
        )
        record.status = record.status or "present"
        _ensure_shift_defaults(record)

        if record.clock_in:
            record.paid_minutes = _compute_minutes(
                record.clock_in, record.clock_out, record.date
            )

        record.save(
            update_fields=[
                "clock_out",
                "clock_out_location",
                "status",
                "paid_minutes",
                "updated_at",
            ]
        )

        punch = AttendancePunch.objects.create(
            attendance=record,
            punch_type=AttendancePunch.TYPE_CHECK_OUT,
            timestamp=now,
            location=record.clock_out_location,
        )

        return Response(
            {
                "record": AttendanceRecordSerializer(record).data,
                "punch": AttendancePunchSerializer(punch).data,
            }
        )


class AttendanceCorrectionView(APIView):
    def patch(self, request, employee_id: int, record_id: int):
        employee = _get_employee_or_404(employee_id)
        _ensure_employee_access(request, employee)

        try:
            record = AttendanceRecord.objects.get(id=record_id, employee=employee)
        except AttendanceRecord.DoesNotExist:
            return Response(
                {"detail": "Attendance record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AttendanceRecordSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AttendancePlaceholderViewSet(viewsets.ViewSet):
    """Placeholder to show /attendances at API root (real routes under /attendances/)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None  # Avoid spectacular warnings

    def list(self, request):  # pragma: no cover - trivial
        return Response({"message": "Attendance API Root"})


class DepartmentAttendanceViewSet(viewsets.ViewSet):
    """Department attendance summary and drill-down (HR/staff only)."""

    def list(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            msg = "Only HR can view department attendance."
            raise PermissionDenied(msg)
        today = timezone.localdate()
        departments = Department.objects.all()

        results = []
        for dept in departments:
            employees = Employee.objects.filter(department=dept, is_active=True)
            present = absent = late = overtime = 0

            for emp in employees:
                record = AttendanceRecord.objects.filter(
                    employee=emp, date=today
                ).first()
                if not record:
                    absent += 1
                    continue

                _ensure_shift_defaults(record)
                status = _attendance_status(record)

                # Late/partial are still present for counting purposes
                if status in {"PRESENT", "LATE", "PARTIAL"} or record.clock_in:
                    present += 1
                else:
                    absent += 1
                if _is_late(record):
                    late += 1
                if record.clock_out and _calculate_paid_minutes(record) > (
                    record.work_schedule_minutes or 0
                ):
                    overtime += 1

            results.append(
                {
                    "department_id": dept.id,
                    "department_name": dept.name,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "overtime": overtime,
                }
            )

        return Response(results)

    def retrieve(self, request, pk: str | None = None):
        today = timezone.localdate()

        try:
            dept = Department.objects.get(id=pk)
        except Department.DoesNotExist as exc:
            msg = "Department not found"
            raise Http404(msg) from exc

        if not (request.user.is_staff or request.user.is_superuser):
            msg = "Only HR can view department attendance."
            raise PermissionDenied(msg)

        employees = Employee.objects.filter(department=dept, is_active=True)
        results = []

        for emp in employees:
            record, _ = AttendanceRecord.objects.get_or_create(
                employee=emp,
                date=today,
                defaults={"status": "pending"},
            )
            _ensure_shift_defaults(record)
            if record.clock_in and record.clock_out:
                record.paid_minutes = _compute_minutes(
                    record.clock_in, record.clock_out, record.date
                )
                record.save(update_fields=["paid_minutes", "updated_at"])
            results.append(_serialize_record(record))

        return Response(results)


def _sync_punch_for_record(record, punch_type, time_value, location_value) -> None:
    desired_ts = _build_timestamp(record, time_value)
    punches = record.punches.filter(punch_type=punch_type)
    if not desired_ts:
        if punches.exists():
            punches.delete()
        return

    punch = punches.first()
    location = location_value or ""
    if punch:
        changed = False
        if punch.timestamp != desired_ts:
            punch.timestamp = desired_ts
            changed = True
        if punch.location != location:
            punch.location = location
            changed = True
        if changed:
            punch.save(update_fields=["timestamp", "location"])
    else:
        AttendancePunch.objects.create(
            attendance=record,
            punch_type=punch_type,
            timestamp=desired_ts,
            location=location,
        )


def _recalculate_record_stats(record, *, status_in_payload: bool = False) -> None:
    paid_minutes = 0
    if record.clock_in and record.clock_out:
        paid_minutes = _compute_minutes(record.clock_in, record.clock_out, record.date)

    update_fields = []
    if record.paid_minutes != paid_minutes:
        record.paid_minutes = paid_minutes
        update_fields.append("paid_minutes")

    if not status_in_payload:
        computed_status = _attendance_status(record)
        # Only auto-update status if it's in a standard state (not manually overridden to something custom/final?)
        # Actually logic was: if current status is one of standard dynamic ones, update it.
        if (record.status or "").lower() in {
            "",
            "pending",
            "present",
            "absent",
            "partial",
        }:
            if record.status != computed_status:
                record.status = computed_status
                update_fields.append("status")

    if update_fields:
        update_fields.append("updated_at")
        record.save(update_fields=update_fields)


class AttendanceRecordAdminViewSet(viewsets.ViewSet):
    """HR/staff attendance corrections."""

    def partial_update(self, request, pk: str | None = None):
        if not (request.user.is_staff or request.user.is_superuser):
            msg = "Only managers can edit attendance records."
            raise PermissionDenied(msg)

        try:
            record = AttendanceRecord.objects.get(id=pk)
        except AttendanceRecord.DoesNotExist as exc:
            msg = "Attendance record not found"
            raise Http404(msg) from exc

        payload = request.data.copy()
        # Allow clearing times by sending empty string/null
        for time_field in ("clock_in", "clock_out"):
            if payload.get(time_field) in ("", None, "null"):
                payload[time_field] = None

        serializer = AttendanceRecordSerializer(record, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        record = serializer.save()

        _ensure_shift_defaults(record)

        _sync_punch_for_record(
            record,
            AttendancePunch.TYPE_CHECK_IN,
            record.clock_in,
            record.clock_in_location,
        )
        _sync_punch_for_record(
            record,
            AttendancePunch.TYPE_CHECK_OUT,
            record.clock_out,
            record.clock_out_location,
        )

        _recalculate_record_stats(
            record, status_in_payload="status" in serializer.validated_data
        )

        return Response(_serialize_record(record))
