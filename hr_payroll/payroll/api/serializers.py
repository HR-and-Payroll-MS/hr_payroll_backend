from rest_framework import serializers

from hr_payroll.payroll.models import Compensation
from hr_payroll.payroll.models import SalaryComponent


class SalaryComponentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalaryComponent
        fields = [
            "id",
            "compensation",
            "kind",
            "amount",
            "label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def get_id(self, obj: SalaryComponent) -> str:  # Align with frontend string ids
        return str(obj.pk)


class CompensationSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)
    # Optionally include components on read; write handled via separate endpoint
    components = SalaryComponentSerializer(many=True, read_only=True)

    class Meta:
        model = Compensation
        fields = [
            "id",
            "employee",
            "total_compensation",
            "components",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("total_compensation", "created_at", "updated_at")

    def get_id(self, obj: Compensation) -> str:
        return str(obj.pk)
