from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from hr_payroll.leaves.models import BalanceHistory
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = "__all__"


class LeavePolicySerializer(serializers.ModelSerializer):
    leave_type_details = LeaveTypeSerializer(source="leave_type", read_only=True)

    class Meta:
        model = LeavePolicy
        fields = "__all__"


class PublicHolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicHoliday
        fields = "__all__"


class EmployeeBalanceSerializer(serializers.ModelSerializer):
    policy_details = LeavePolicySerializer(source="policy", read_only=True)
    available_days = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )

    class Meta:
        model = EmployeeBalance
        fields = "__all__"
        read_only_fields = (
            "entitled_days",
            "used_days",
            "pending_days",
            "carry_forward_days",
        )


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = "__all__"
        read_only_fields = ("status", "rejection_reason", "employee")

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and start_date > end_date:
            msg = _("Start date cannot be after end date.")
            raise serializers.ValidationError(msg)
        return attrs


class BalanceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceHistory
        fields = "__all__"
        read_only_fields = ("changed_by",)
