from rest_framework import serializers

from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollGeneralSetting
from hr_payroll.payroll.models import PayrollRun
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipDocument
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.payroll.models import TaxCode
from hr_payroll.payroll.models import TaxCodeVersion


class BankMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankMaster
        fields = ["id", "name", "swift_code", "code"]


class SalaryComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryComponent
        fields = ["id", "name", "component_type", "is_taxable", "is_recurring"]


class PayrollGeneralSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollGeneralSetting
        fields = ["id", "currency", "proration_policy", "working_days_basis"]


class SalaryStructureItemSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = SalaryStructureItem
        fields = ["id", "component", "component_name", "amount"]


class EmployeeSalaryStructureSerializer(serializers.ModelSerializer):
    items = SalaryStructureItemSerializer(many=True, read_only=True)
    employee_name = serializers.CharField(source="employee.user.name", read_only=True)

    class Meta:
        model = EmployeeSalaryStructure
        fields = [
            "id",
            "employee",
            "employee_name",
            "base_salary",
            "items",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class BankDetailSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source="bank.name", read_only=True)
    employee_name = serializers.CharField(source="employee.user.name", read_only=True)

    class Meta:
        model = BankDetail
        fields = [
            "id",
            "employee",
            "employee_name",
            "bank",
            "bank_name",
            "branch_name",
            "account_holder",
            "account_number",
            "iban",
        ]


class DependentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.user.name", read_only=True)

    class Meta:
        model = Dependent
        fields = [
            "id",
            "employee",
            "employee_name",
            "name",
            "relationship",
            "date_of_birth",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayCycleSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(
        source="manager_in_charge.user.name", read_only=True, allow_null=True
    )
    total_payout = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PayCycle
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "cutoff_date",
            "manager_in_charge",
            "manager_name",
            "status",
            "total_payout",
            "employee_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayslipLineItemSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(
        source="component.name", read_only=True, allow_null=True
    )

    class Meta:
        model = PayslipLineItem
        fields = ["id", "component", "component_name", "label", "amount", "category"]


class PayrollSlipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.user.name", read_only=True)
    cycle_name = serializers.CharField(source="cycle.name", read_only=True)
    line_items = PayslipLineItemSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollSlip
        fields = [
            "id",
            "cycle",
            "cycle_name",
            "employee",
            "employee_name",
            "base_salary",
            "total_earnings",
            "total_deductions",
            "net_pay",
            "total_work_duration",
            "total_overtime_duration",
            "total_deficit_duration",
            "status",
            "line_items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayslipDocumentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.user.name", read_only=True)
    cycle_name = serializers.CharField(
        source="cycle.name", read_only=True, allow_null=True
    )
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = PayslipDocument
        fields = [
            "id",
            "employee",
            "employee_name",
            "cycle",
            "cycle_name",
            "month",
            "file",
            "gross",
            "net",
            "uploaded_by",
            "uploaded_by_name",
            "uploaded_at",
        ]
        read_only_fields = ["uploaded_at", "uploaded_by"]


class TaxCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxCode
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class TaxCodeVersionSerializer(serializers.ModelSerializer):
    tax_code_code = serializers.CharField(source="tax_code.code", read_only=True)

    class Meta:
        model = TaxCodeVersion
        fields = [
            "id",
            "tax_code",
            "tax_code_code",
            "effective_from",
            "effective_to",
            "rate",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayrollRunSerializer(serializers.ModelSerializer):
    cycle_name = serializers.CharField(source="cycle.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, allow_null=True
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True, allow_null=True
    )
    finalized_by_name = serializers.CharField(
        source="finalized_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "cycle",
            "cycle_name",
            "status",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "finalized_by",
            "finalized_by_name",
            "approved_at",
            "finalized_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "approved_by",
            "finalized_by",
            "approved_at",
            "finalized_at",
            "created_at",
            "updated_at",
        ]


class PayrollReportRowSerializer(serializers.Serializer):
    """Serializer for aggregated payroll report rows.

    Uses snake_case internally to satisfy linting, then outputs camelCase
    for frontend compatibility via `to_representation`.
    """

    cycle_id = serializers.IntegerField(required=False, allow_null=True)
    cycle_name = serializers.CharField(required=False, allow_null=True)
    employee_id = serializers.IntegerField()
    employee_name = serializers.CharField(allow_null=True)
    base_salary = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
    total_earnings = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
    total_deductions = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
    gross = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    net = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    source = serializers.ChoiceField(choices=["slip", "document"])

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "cycleId": data.get("cycle_id"),
            "cycleName": data.get("cycle_name"),
            "employeeId": data.get("employee_id"),
            "employeeName": data.get("employee_name"),
            "baseSalary": data.get("base_salary"),
            "totalEarnings": data.get("total_earnings"),
            "totalDeductions": data.get("total_deductions"),
            "gross": data.get("gross"),
            "net": data.get("net"),
            "source": data.get("source"),
        }
