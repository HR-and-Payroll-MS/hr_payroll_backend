from datetime import date
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError

from hr_payroll.employees.models import Employee
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
from hr_payroll.users.models import User

pytestmark = pytest.mark.django_db


class TestBankMaster:
    def test_create_bank_master(self):
        bank = BankMaster.objects.create(
            name="Chase Bank", swift_code="CHASUS33", code="021000021"
        )
        assert bank.name == "Chase Bank"
        assert bank.swift_code == "CHASUS33"
        assert str(bank) == "Chase Bank"

    def test_bank_name_unique(self):
        BankMaster.objects.create(name="Chase Bank")
        with pytest.raises(IntegrityError):
            BankMaster.objects.create(name="Chase Bank")


class TestSalaryComponent:
    def test_create_salary_component_earning(self):
        comp = SalaryComponent.objects.create(
            name="Basic Salary",
            component_type="earning",
            is_taxable=True,
            is_recurring=True,
        )
        assert comp.name == "Basic Salary"
        assert comp.component_type == "earning"
        assert comp.is_taxable is True
        assert str(comp) == "Basic Salary (earning)"

    def test_create_salary_component_deduction(self):
        comp = SalaryComponent.objects.create(
            name="Tax", component_type="deduction", is_taxable=False, is_recurring=True
        )
        assert comp.component_type == "deduction"
        assert comp.is_taxable is False


class TestEmployeeSalaryStructure:
    def test_create_salary_structure(self, employee):
        structure = EmployeeSalaryStructure.objects.create(
            employee=employee, base_salary=Decimal("5000.00")
        )
        assert structure.employee == employee
        assert structure.base_salary == Decimal("5000.00")
        assert str(structure) == f"Structure: {employee}"

    def test_salary_structure_with_components(self, employee):
        structure = EmployeeSalaryStructure.objects.create(
            employee=employee, base_salary=Decimal("5000.00")
        )
        transport = SalaryComponent.objects.create(
            name="Transport", component_type="earning", is_recurring=True
        )
        SalaryStructureItem.objects.create(
            structure=structure, component=transport, amount=Decimal("500.00")
        )
        assert structure.components.count() == 1
        assert structure.components.first() == transport


class TestPayCycle:
    def test_create_pay_cycle(self, employee):
        cycle = PayCycle.objects.create(
            name="January 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            cutoff_date=date(2025, 1, 25),
            manager_in_charge=employee,
            status="draft",
        )
        assert cycle.name == "January 2025"
        assert cycle.status == "draft"
        assert str(cycle) == "January 2025 (2025-01-01 to 2025-01-31)"


class TestPayrollSlip:
    def test_create_payroll_slip(self, employee):
        cycle = PayCycle.objects.create(
            name="January 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            cutoff_date=date(2025, 1, 25),
            status="draft",
        )
        slip = PayrollSlip.objects.create(
            cycle=cycle,
            employee=employee,
            base_salary=Decimal("5000.00"),
            total_earnings=Decimal("5500.00"),
            total_deductions=Decimal("500.00"),
            net_pay=Decimal("5000.00"),
            total_work_duration=timedelta(hours=160),
            total_overtime_duration=timedelta(hours=10),
            status="draft",
        )
        assert slip.employee == employee
        assert slip.base_salary == Decimal("5000.00")
        assert slip.net_pay == Decimal("5000.00")
        assert slip.total_work_duration == timedelta(hours=160)

    def test_payroll_slip_unique_constraint(self, employee):
        cycle = PayCycle.objects.create(
            name="January 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            cutoff_date=date(2025, 1, 25),
            status="draft",
        )
        PayrollSlip.objects.create(
            cycle=cycle, employee=employee, base_salary=Decimal("5000.00")
        )
        with pytest.raises(IntegrityError):
            PayrollSlip.objects.create(
                cycle=cycle, employee=employee, base_salary=Decimal("5000.00")
            )


class TestPayslipLineItem:
    def test_create_line_item(self, employee):
        cycle = PayCycle.objects.create(
            name="January 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            cutoff_date=date(2025, 1, 25),
            status="draft",
        )
        slip = PayrollSlip.objects.create(
            cycle=cycle, employee=employee, base_salary=Decimal("5000.00")
        )
        component = SalaryComponent.objects.create(
            name="Transport", component_type="earning"
        )
        line = PayslipLineItem.objects.create(
            slip=slip,
            component=component,
            label="Transport Allowance",
            amount=Decimal("500.00"),
            category="recurring",
        )
        assert line.slip == slip
        assert line.amount == Decimal("500.00")
        assert line.category == "recurring"


class TestBankDetail:
    def test_create_bank_detail(self, employee):
        bank = BankMaster.objects.create(name="Chase Bank", swift_code="CHASUS33")
        detail = BankDetail.objects.create(
            employee=employee,
            bank=bank,
            branch_name="Downtown Branch",
            account_holder="John Doe",
            account_number="1234567890",
            iban="US12345678901234567890",
        )
        assert detail.employee == employee
        assert detail.bank == bank
        assert detail.account_number == "1234567890"
        assert str(detail) == f"{employee} - Chase Bank"


class TestDependent:
    def test_create_dependent(self, employee):
        dependent = Dependent.objects.create(
            employee=employee,
            name="Jane Doe",
            relationship="Spouse",
            date_of_birth=date(1990, 5, 15),
        )
        assert dependent.employee == employee
        assert dependent.name == "Jane Doe"
        assert dependent.relationship == "Spouse"


class TestPayrollGeneralSetting:
    def test_singleton_setting(self):
        setting1 = PayrollGeneralSetting.objects.create(
            currency="USD", proration_policy="fixed_day", working_days_basis=20
        )
        # Should update the existing record, not create a new one
        setting1.currency = "EUR"
        setting1.proration_policy = "actual_days"
        setting1.working_days_basis = 22
        setting1.save()
        # Should only have one record (singleton pattern)
        assert setting1.pk == 1
        assert PayrollGeneralSetting.objects.count() == 1
        latest = PayrollGeneralSetting.objects.get(pk=1)
        assert latest.currency == "EUR"
        assert latest.proration_policy == "actual_days"
        assert latest.working_days_basis == 22


@pytest.fixture
def employee():
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",  # noqa: S106
    )
    return Employee.objects.create(user=user, employee_id="E-00001", title="Engineer")
