from rest_framework import serializers

from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollGeneralSetting
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem


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
