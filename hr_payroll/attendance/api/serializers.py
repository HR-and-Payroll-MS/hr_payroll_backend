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


class AttendanceCorrectionSerializer(serializers.ModelSerializer):
    """Limited edit serializer for manager/line-manager corrections.

    Allows updating time/location fields and notes only.
    """

    class Meta:
        model = Attendance
        fields = [
            "clock_in",
            "clock_in_location",
            "clock_out",
            "clock_out_location",
            "notes",
        ]
        extra_kwargs = {
            "clock_in": {"required": False, "allow_null": True},
            "clock_in_location": {"required": False, "allow_blank": True},
            "clock_out": {"required": False, "allow_null": True},
            "clock_out_location": {"required": False, "allow_blank": True},
            "notes": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        attrs = dict(attrs)
        inst = getattr(self, "instance", None)
        clock_in = (
            attrs.get("clock_in")
            if "clock_in" in attrs
            else getattr(inst, "clock_in", None)
        )
        clock_out = (
            attrs.get("clock_out")
            if "clock_out" in attrs
            else getattr(inst, "clock_out", None)
        )
        # Prevent impossible state: clock_out without clock_in.
        if clock_in is None and clock_out is not None:
            raise serializers.ValidationError(
                {"clock_in": "clock-in is required when clock-out is set."}
            )
        if clock_in and clock_out and clock_out < clock_in:
            raise serializers.ValidationError(
                {"clock_out": "Clock-out cannot be before clock-in."}
            )
        return attrs


class FingerprintScanSerializer(serializers.Serializer):
    fingerprint_token = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    timestamp = serializers.DateTimeField(required=False)


class EmployeeClockInSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    clock_in = serializers.DateTimeField(required=False)
    # For consistency with clock-out and older clients.
    timestamp = serializers.DateTimeField(required=False)
    clock_in_location = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = dict(attrs)
        if not (attrs.get("clock_in_location") or ""):
            alias = attrs.get("location")
            if isinstance(alias, str) and alias.strip():
                attrs["clock_in_location"] = alias

        if attrs.get("clock_in") is None and attrs.get("timestamp") is not None:
            attrs["clock_in"] = attrs["timestamp"]

        loc = attrs.get("clock_in_location")
        if not isinstance(loc, str) or not loc.strip():
            raise serializers.ValidationError({"clock_in_location": "required"})

        return attrs


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


class SelfClockOutSerializer(serializers.Serializer):
    """Clock-out payload without attendance id.

    Backend resolves the record by (employee_id, date).
    """

    # Frontend historically used `clock_out_location`.
    location = serializers.CharField(required=False, allow_blank=True)
    clock_out_location = serializers.CharField(required=False, allow_blank=True)
    date = serializers.DateField(required=False)
    time = serializers.TimeField(required=False)
    timestamp = serializers.DateTimeField(required=False)
    # Some clients may send the explicit datetime as `clock_out`.
    clock_out = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = dict(attrs)
        if not (attrs.get("location") or ""):
            alias = attrs.get("clock_out_location")
            if isinstance(alias, str) and alias.strip():
                attrs["location"] = alias

        if attrs.get("timestamp") is None and attrs.get("clock_out") is not None:
            attrs["timestamp"] = attrs["clock_out"]

        location = attrs.get("location")
        if not isinstance(location, str) or not location.strip():
            raise serializers.ValidationError({"location": "required"})

        return attrs


class DepartmentAttendanceSummarySerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    date = serializers.DateField()
    total_employees = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    permitted = serializers.IntegerField()


class DepartmentEmployeeAttendanceRowSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    employee_name = serializers.CharField()
    date = serializers.DateField()
    attendance_id = serializers.IntegerField(allow_null=True)
    clock_in = serializers.DateTimeField(allow_null=True)
    clock_in_location = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    clock_out = serializers.DateTimeField(allow_null=True)
    clock_out_location = serializers.CharField(allow_blank=True)
    work_schedule_hours = serializers.IntegerField()
    paid_time = serializers.DurationField()
    notes = serializers.CharField(allow_blank=True)
