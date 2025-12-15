from rest_framework import serializers

from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment


class AttendanceSerializer(serializers.ModelSerializer):
    logged_time = serializers.SerializerMethodField(read_only=True)
    deficit = serializers.SerializerMethodField(read_only=True)
    overtime = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "employee",
            "date",
            "clock_in",
            "clock_in_location",
            "clock_out",
            "clock_out_location",
            "work_schedule_hours",
            "logged_time",
            "paid_time",
            "deficit",
            "overtime",
            "overtime_seconds",
            "notes",
            "status",
        ]
        read_only_fields = [
            "logged_time",
            "deficit",
            "overtime",
            "overtime_seconds",
            "status",
        ]

    def get_logged_time(self, obj) -> str | None:
        lt = obj.logged_time
        if lt is None:
            return None
        total_seconds = int(lt.total_seconds())
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_deficit(self, obj) -> str | None:
        d = obj.deficit
        if d is None:
            return None
        total_seconds = int(d.total_seconds())
        sign = "-" if total_seconds < 0 else "+"
        total_seconds = abs(total_seconds)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_overtime(self, obj) -> str | None:
        ot = getattr(obj, "overtime", None)
        if ot is None:
            return None
        total_seconds = int(ot.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"


class AttendanceAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceAdjustment
        fields = [
            "id",
            "attendance",
            "performed_by",
            "previous_paid_time",
            "new_paid_time",
            "notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class FingerprintScanSerializer(serializers.Serializer):
    fingerprint_token = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    timestamp = serializers.DateTimeField(required=False)


class EmployeeClockInSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    clock_in = serializers.DateTimeField(required=False)
    clock_in_location = serializers.CharField()


class ManualEntrySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    clock_in = serializers.DateTimeField(required=False)
    clock_in_location = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)


class SelfAttendanceQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class SelfAttendanceActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["check_in", "check_out"])
    location = serializers.CharField()
    date = serializers.DateField(required=False)
    time = serializers.TimeField(required=False)
    timestamp = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
