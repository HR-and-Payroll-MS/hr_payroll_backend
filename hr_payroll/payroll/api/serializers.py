from rest_framework import serializers

from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import Compensation
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import PayrollCycle
from hr_payroll.payroll.models import PayrollRecord
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


class BankDetailSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BankDetail
        fields = [
            "id",
            "employee",
            "bank_name",
            "branch",
            "swift_bic",
            "account_name",
            "account_number",
            "iban",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def get_id(self, obj: BankDetail) -> str:
        return str(obj.pk)


class DependentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Dependent
        fields = [
            "id",
            "employee",
            "name",
            "relationship",
            "date_of_birth",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def get_id(self, obj: Dependent) -> str:
        return str(obj.pk)


class PayrollCycleSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PayrollCycle
        fields = [
            "id",
            "name",
            "description",
            "frequency",
            "person_in_charge",
            "period_start",
            "period_end",
            "cutoff_date",
            "review_cutoff_date",
            "review_cutoff_enabled",
            "eligibility_criteria",
            "eligible_employees",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def get_id(self, obj: PayrollCycle) -> str:
        return str(obj.pk)


class PayrollRecordSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True)
    employee = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PayrollRecord
        fields = [
            "id",
            "cycle",
            "employee",
            "salary",
            "actual",
            "recurring",
            "one_off",
            "offset",
            "ot",
            "total_compensation",
            "period_start",
            "period_end",
            "actual_work_seconds",
            "overtime_seconds",
            "deficit_seconds",
            "carry_over_overtime_seconds",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at", "total_compensation")

    def get_id(self, obj: PayrollRecord) -> str:
        return str(obj.pk)
