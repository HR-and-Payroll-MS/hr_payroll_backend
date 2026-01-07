import os
import random
from datetime import date
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from hr_payroll.employees.models import Contract
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import JobHistory
from hr_payroll.org.models import Department
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.payroll.models import TaxCode
from hr_payroll.payroll.models import TaxCodeVersion


def seed():
    # 1. Banks
    bank, _ = BankMaster.objects.get_or_create(
        name="Commercial Bank of Ethiopia",
        defaults={"swift_code": "CBETETAA", "code": "1000"},
    )

    # 2. Departments
    dept_names = [
        "Computer Science",
        "Engineering",
        "Human Resources",
        "Finance",
        "Marketing",
    ]
    departments = []
    for name in dept_names:
        d, _ = Department.objects.get_or_create(name=name)
        departments.append(d)

    # 3. Components
    basic, _ = SalaryComponent.objects.get_or_create(
        name="Basic Salary", defaults={"component_type": "earning", "is_taxable": True}
    )
    transport, _ = SalaryComponent.objects.get_or_create(
        name="Transport Allowance",
        defaults={"component_type": "earning", "is_taxable": False},
    )
    housing, _ = SalaryComponent.objects.get_or_create(
        name="Housing Allowance",
        defaults={"component_type": "earning", "is_taxable": True},
    )

    # 4. Tax Code
    it_code, _ = TaxCode.objects.get_or_create(
        code="IT-001", defaults={"name": "Income Tax", "is_active": True}
    )
    if not it_code.versions.exists():
        TaxCodeVersion.objects.create(
            tax_code=it_code, effective_from=date(2020, 1, 1), rate=Decimal("0.15")
        )

    # 5. Employees
    employees = Employee.objects.all()

    roles = [
        "Software Engineer",
        "Senior Developer",
        "HR Manager",
        "Accountant",
        "Product Owner",
    ]

    for emp in employees:
        # --- Update Employee Core Fields ---
        if not emp.department:
            emp.department = random.choice(departments)

        if not emp.title:
            emp.title = random.choice(roles)

        if not emp.join_date:
            emp.join_date = date(2020, 1, 1)

        if not emp.employee_id:
            possible_id = f"E-{emp.pk:05d}"
            if Employee.objects.filter(employee_id=possible_id).exists():
                possible_id = f"E-{emp.pk:05d}-B"  # Fallback
            emp.employee_id = possible_id

        emp.save()

        # --- Job History ---
        # Ensure at least one job history exists
        if not JobHistory.objects.filter(employee=emp).exists():
            JobHistory.objects.create(
                employee=emp,
                effective_date=emp.join_date,
                job_title=emp.title,
                position_type="IC",
                employment_type="fulltime",
            )

        # --- Contract ---
        if not Contract.objects.filter(employee=emp).exists():
            Contract.objects.create(
                employee=emp,
                contract_number=f"CN-{emp.pk:04d}",
                contract_name="Standard Permanent",
                contract_type="Permanent",
                start_date=emp.join_date,
            )

        # --- Bank Detail ---
        if not hasattr(emp, "bank_detail"):
            BankDetail.objects.create(
                employee=emp,
                bank=bank,
                account_holder=f"{emp.user.username.upper()}",
                account_number=f"1000{random.randint(100000, 999999)}",
            )

        # --- Salary Structure ---
        structure, created = EmployeeSalaryStructure.objects.get_or_create(
            employee=emp, defaults={"base_salary": Decimal("0.00")}
        )

        # Clear existing items to force refresh with new randoms
        structure.items.all().delete()

        # Random Salary between 80000 and 150000 (higher values)
        base = random.randint(80, 150) * 1000
        trans = random.choice([2000, 3000, 5000])
        house = random.choice([3000, 5000, 0])

        structure.base_salary = Decimal(base)
        structure.save()

        SalaryStructureItem.objects.create(
            structure=structure, component=transport, amount=Decimal(trans)
        )
        if house > 0:
            SalaryStructureItem.objects.create(
                structure=structure, component=housing, amount=Decimal(house)
            )


if __name__ == "__main__":
    seed()
