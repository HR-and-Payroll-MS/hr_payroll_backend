from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from hr_payroll.attendance.models import AttendancePunch
from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.policies import accessors as policy_accessors


class AttendancePunchSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()

    class Meta:
        model = AttendancePunch
        fields = ["type", "time", "location"]
        read_only_fields = fields

    def get_type(self, obj: AttendancePunch) -> str:
        return obj.punch_type

    def get_time(self, obj: AttendancePunch) -> str:
        # ISO string for frontend timeline display
        return obj.timestamp.isoformat()


class AttendanceRecordSerializer(serializers.ModelSerializer):
    punches = AttendancePunchSerializer(many=True, read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "date",
            "shift_name",
            "shift_start",
            "shift_end",
            "clock_in",
            "clock_out",
            "clock_in_location",
            "clock_out_location",
            "paid_minutes",
            "work_schedule_minutes",
            "status",
            "notes",
            "punches",
        ]
        read_only_fields = [
            "date",
            "paid_minutes",
            "work_schedule_minutes",
            "punches",
        ]

    def validate(self, attrs):
        instance: AttendanceRecord = self.instance
        if not instance:
            return attrs

        window_days = policy_accessors.attendance_edit_window_days()
        cutoff = timezone.localdate() - timedelta(days=window_days)
        if instance.date < cutoff:
            raise serializers.ValidationError(
                {
                    "date": f"Attendance edits only allowed for the last {window_days} days.",
                }
            )
        return attrs
