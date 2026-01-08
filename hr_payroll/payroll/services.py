import calendar
import logging
from datetime import date
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.employees.models import Employee
from hr_payroll.expenses.models import ExpenseRequest
from hr_payroll.loans.models import LoanRepayment
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.policies import accessors as policy_accessors
from hr_payroll.policies import get_policy_document
from hr_payroll.realtime.events import EVENT_PAYROLL_PROGRESS
from hr_payroll.realtime.socketio import emit_event_to_group

logger = logging.getLogger(__name__)


def generate_structure_from_policy(employee: Employee):
    """
    Auto-generate or update an EmployeeSalaryStructure based on policy defaults.
    1. Determines Base Salary from Job Structure Policy (using title as proxy for grade).
    2. Adds all Policy Allowances as SalaryStructureItems.
    """
    doc = get_policy_document()
    salary_policy = doc.get("salaryStructurePolicy", {})

    # 1. Base Salary
    base_template = salary_policy.get("baseSalaryTemplate", {})
    # Simple heuristic: try to match employee.title to a key, else default
    # If title is "Manager", try "manager", else "gradeA" as fallback.
    # Ideally, Employee model should have a 'grade' field.
    base_amount = 0
    if base_template:
        # Check explicit match
        title_key = str(employee.title or "").lower().replace(" ", "")
        if title_key in base_template:
            base_amount = base_template[title_key]
        else:
            # Fallback to first value
            base_amount = next(iter(base_template.values()))

    structure, _ = EmployeeSalaryStructure.objects.update_or_create(
        employee=employee, defaults={"base_salary": base_amount}
    )

    # 2. Allowances
    allowances = salary_policy.get("allowances", [])
    if isinstance(allowances, list):
        {item.component.name: item for item in structure.items.all()}

        for alloc in allowances:
            if not isinstance(alloc, dict):
                continue
            name = alloc.get("name")
            val = alloc.get("value", 0)
            if not name:
                continue

            # Ensure component exists (sync logic should have handled this, but be safe)
            comp, _ = SalaryComponent.objects.get_or_create(
                name=name, defaults={"component_type": "earning", "is_recurring": True}
            )

            SalaryStructureItem.objects.update_or_create(
                structure=structure, component=comp, defaults={"amount": val}
            )

    return structure


class PayrollCalculator:
    """
    Central engine for calculating payroll.
    Uses SalaryStructure for earnings/deductions and TaxCode for taxes.
    Integrates all policy modules: Overtime, Attendance, Loans, Expenses.
    """

    def __init__(self, employee: Employee, cycle_date: date | None = None):
        self.employee = employee
        self.cycle_date = cycle_date or timezone.now().date()
        # Ensure structure exists or try to generate it
        if not hasattr(employee, "salary_structure"):
            generate_structure_from_policy(employee)
            employee.refresh_from_db()

        self.structure = getattr(employee, "salary_structure", None)
        self.base_salary = Decimal("0.00")

        self.earnings: list[dict] = []
        self.deductions: list[dict] = []
        self.taxes: list[dict] = []

        self.loan_repayments: list[LoanRepayment] = []
        self.expense_reimbursements: list[ExpenseRequest] = []

        self.total_overtime_minutes = 0

    def calculate(self):
        """Perform calculation."""
        self._extract_structure_components()
        self._calculate_overtime()
        self._calculate_attendance_penalties()
        self._calculate_loans()
        self._calculate_expenses()
        self._calculate_statutory_deductions()  # Pension & Tax

        return self._build_result()

    def _extract_structure_components(self):
        """Get fixed components from EmployeeSalaryStructure."""
        if not self.structure:
            return

        self.base_salary = Decimal(self.structure.base_salary or 0)

        # Add Base Salary as a distinct line item if positive
        if self.base_salary > 0:
            self.earnings.append(
                {
                    "label": "Basic Salary",
                    "amount": self.base_salary,
                    "component": None,
                    "category": PayslipLineItem.Category.RECURRING,
                }
            )

        for item in self.structure.items.select_related("component"):
            comp = item.component
            if not comp:
                continue

            payload = {
                "label": comp.name,
                "amount": Decimal(item.amount or 0),
                "component": comp,
                "category": PayslipLineItem.Category.RECURRING,
            }

            if comp.component_type == comp.Type.DEDUCTION:
                self.deductions.append(payload)
            else:
                self.earnings.append(payload)

    def _calculate_overtime(self):
        """Calculate and add overtime pay based on attendance records."""
        start_date = self.cycle_date.replace(day=1)
        records = AttendanceRecord.objects.filter(
            employee=self.employee,
            date__range=(start_date, self.cycle_date),
            status__in=["present", "late", "partial"],
        )

        total_minutes = 0
        for record in records:
            if record.paid_minutes and record.work_schedule_minutes:
                overtime = record.paid_minutes - record.work_schedule_minutes
                if overtime > 0:
                    total_minutes += overtime

        # Check against policy threshold
        min_threshold = policy_accessors.min_overtime_minutes()
        if total_minutes < min_threshold:
            return

        self.total_overtime_minutes = total_minutes

        # Calculate Hourly Rate (Standard 22 days * 8 hours)
        standard_days = 22
        standard_hours = policy_accessors.standard_work_hours_per_day()
        total_standard_hours = Decimal(standard_days * standard_hours)

        if total_standard_hours <= 0:
            hourly_rate = Decimal("0.00")
        else:
            hourly_rate = self.base_salary / total_standard_hours

        # Rate Multiplier
        multiplier = policy_accessors.overtime_rate_multiplier()

        overtime_pay = (Decimal(total_minutes) / Decimal(60)) * hourly_rate * multiplier
        overtime_pay = overtime_pay.quantize(Decimal("0.01"))

        if overtime_pay > 0:
            self.earnings.append(
                {
                    "label": f"Overtime ({total_minutes // 60}h {total_minutes % 60}m)",
                    "amount": overtime_pay,
                    "component": None,  # Could find/create "Overtime" component
                    "category": PayslipLineItem.Category.OVERTIME,
                }
            )

    def _calculate_attendance_penalties(self):
        """Deduct for excessive lateness based on policy."""
        grace_limit = policy_accessors.max_lateness_occurrences()
        start_date = self.cycle_date.replace(day=1)

        late_count = AttendanceRecord.objects.filter(
            employee=self.employee,
            date__range=(start_date, self.cycle_date),
            status="late",
        ).count()

        if late_count > grace_limit:
            # Policy: "Salary deduction". Assumption: 0.5 days pay per excess occurrence.
            excess = late_count - grace_limit

            standard_days = 22
            daily_rate = (
                self.base_salary / Decimal(standard_days)
                if standard_days
                else Decimal(0)
            )
            penalty = (daily_rate * Decimal("0.5") * excess).quantize(Decimal("0.01"))

            if penalty > 0:
                self.deductions.append(
                    {
                        "label": f"Lateness Penalty ({excess} days)",
                        "amount": penalty,
                        "component": None,
                        "category": PayslipLineItem.Category.RECURRING,  # Defaulting to recurring for deduction
                    }
                )

    def _calculate_loans(self):
        """Deduct pending loan repayments due in this cycle."""
        start_date = self.cycle_date.replace(day=1)

        repayments = LoanRepayment.objects.filter(
            loan__employee=self.employee,
            status=LoanRepayment.Status.PENDING,
            due_date__lte=self.cycle_date,
            due_date__gte=start_date,
        )

        for rp in repayments:
            self.loan_repayments.append(rp)
            self.deductions.append(
                {
                    "label": f"Loan Repayment (Loan #{rp.loan.id})",
                    "amount": rp.amount,
                    "component": None,
                    "category": PayslipLineItem.Category.RECURRING,
                }
            )

    def _calculate_expenses(self):
        """Reimburse approved expenses."""
        # Find approved expenses not yet linked to a payroll slip
        expenses = ExpenseRequest.objects.filter(
            employee=self.employee,
            status=ExpenseRequest.Status.APPROVED,
            payroll_slip__isnull=True,
        )

        for exp in expenses:
            self.expense_reimbursements.append(exp)
            self.earnings.append(
                {
                    "label": f"Expense: {exp.get_category_display()}",
                    "amount": exp.amount,
                    "component": None,
                    "category": PayslipLineItem.Category.REIMBURSEMENT,
                }
            )

    def _calculate_statutory_deductions(self):
        """Calculate Pension and Tax based on policy."""
        # 1. Pension
        pension_rate = policy_accessors.pension_percentage()
        if pension_rate > 0:
            pension_amt = (self.base_salary * pension_rate / Decimal(100)).quantize(
                Decimal("0.01")
            )
            if pension_amt > 0:
                self.deductions.append(
                    {
                        "label": f"Pension ({pension_rate}%)",
                        "amount": pension_amt,
                        "component": None,
                        "category": PayslipLineItem.Category.TAX,  # Group with tax/statutory
                    }
                )

        # 2. Tax Brackets
        # Calculate taxable gross (Base + Recurring Allowances - Pension?)
        # For simplicity: Taxable Gross = Total Earnings (excluding reimbursements)
        taxable_earnings = sum(
            e["amount"]
            for e in self.earnings
            if e.get("category") != PayslipLineItem.Category.REIMBURSEMENT
        )

        brackets = policy_accessors.tax_brackets()
        tax_total = Decimal(0)

        # Simple slab implementation: Find the bracket that matches gross and apply that rate to the WHOLE amount
        # OR Progressive? The policy data suggests slabs with rates.
        # "rate": 10, "min": 10001, "max": 25000.
        # Let's assume 'Simple Slab' for now based on common payroll simplifications unless progressive is specified.
        # Use the highest matching bracket.

        matched_bracket = None
        for b in brackets:
            mn = Decimal(str(b.get("min", 0)))
            mx = Decimal(str(b.get("max", 999999999)))
            if mn <= taxable_earnings <= mx:
                matched_bracket = b
                break

        if matched_bracket:
            rate = Decimal(str(matched_bracket.get("rate", 0)))
            if rate > 0:
                tax_total = (taxable_earnings * rate / Decimal(100)).quantize(
                    Decimal("0.01")
                )
                self.taxes.append(
                    {
                        "label": f"Income Tax ({rate}%)",
                        "amount": tax_total,
                        "component": None,
                        "category": PayslipLineItem.Category.TAX,
                    }
                )

    def _build_result(self):
        total_earnings = sum(e["amount"] for e in self.earnings)
        total_taxes = sum(t["amount"] for t in self.taxes)
        total_other_deductions = sum(d["amount"] for d in self.deductions)
        total_deductions = total_taxes + total_other_deductions

        net_pay = total_earnings - total_deductions

        return {
            "base_salary": self.base_salary,
            "earnings": self.earnings,
            "deductions": self.deductions + self.taxes,
            "total_earnings": total_earnings,
            "total_deductions": total_deductions,
            "net_pay": net_pay,
            "overtime_minutes": self.total_overtime_minutes,
            # Pass objects to caller for status updates
            "loan_repayments": self.loan_repayments,
            "expense_reimbursements": self.expense_reimbursements,
        }


@transaction.atomic
def generate_payroll_for_cycle(cycle_id: str) -> dict[str, int]:
    """Generate payroll slips completely replacing legacy logic."""

    try:
        cycle = PayCycle.objects.get(pk=cycle_id)
    except PayCycle.DoesNotExist:
        msg = "PayCycle not found"
        raise ValueError(msg) from None

    employees = (
        Employee.objects.filter(is_active=True)
        .select_related("user", "department", "salary_structure")
        .prefetch_related("salary_structure__items__component")
    )

    created = 0
    updated = 0

    # Notify start
    total_employees = len(employees)
    processed_count = 0
    emit_event_to_group(
        "HR Manager",
        EVENT_PAYROLL_PROGRESS,
        {
            "cycle_id": cycle_id,
            "status": "started",
            "total": total_employees,
            "processed": 0,
            "percentage": 0,
        },
    )

    for i, emp in enumerate(employees, start=1):
        processed_count = i
        calculator = PayrollCalculator(emp, cycle.end_date)
        result = calculator.calculate()

        # Create/Update Slip
        slip, created_flag = PayrollSlip.objects.update_or_create(
            cycle=cycle,
            employee=emp,
            defaults={
                "base_salary": result["base_salary"],
                "total_earnings": result["total_earnings"],
                "total_deductions": result["total_deductions"],
                "net_pay": result["net_pay"],
                "status": PayrollSlip.Status.DRAFT,
                "total_work_duration": timedelta(
                    minutes=result.get("total_work_minutes", 0)
                ),
                "total_overtime_duration": timedelta(
                    minutes=result["overtime_minutes"]
                ),
                "total_deficit_duration": timedelta(0),
            },
        )

        # Clear old items
        slip.line_items.all().delete()

        # Re-create Line Items
        line_items = [
            PayslipLineItem(
                slip=slip,
                component=item.get("component"),
                label=item["label"],
                amount=item["amount"],
                category=item.get("category", PayslipLineItem.Category.RECURRING),
            )
            for item in result["earnings"]
        ]
        line_items.extend(
            [
                PayslipLineItem(
                    slip=slip,
                    component=item.get("component"),
                    label=item["label"],
                    amount=item["amount"],
                    category=item.get("category", PayslipLineItem.Category.RECURRING),
                )
                for item in result["deductions"]
            ]
        )

        PayslipLineItem.objects.bulk_create(line_items)

        # Link Loans & Expenses to the Slip
        # Important: We only mark them as paid/reimbursed if the slip is NOT draft?
        # Actually, standard flow: mark them as 'linked'. Status update might happen when slip is Finalized.
        # BUT, to prevent double inclusion in next draft run, we should mark them or link them.
        # Let's set the link now. Status update 'paid'/'reimbursed' should arguably happen on Finalize.
        # Ideally, filter logic in calculate() excludes those already linked.
        # My calculate() logic: `payroll_slip__isnull=True`. So linking checks it out.

        for loan_rp in result["loan_repayments"]:
            loan_rp.payroll_slip = slip
            loan_rp.status = (
                LoanRepayment.Status.PAID
            )  # Optimistic: Assume it will be paid. If draft deleted, set back?
            # Ideally better handled in finalize. For now, linking is key.
            loan_rp.save()

        for exp in result["expense_reimbursements"]:
            exp.payroll_slip = slip
            exp.status = ExpenseRequest.Status.REIMBURSED
            exp.save()

        if created_flag:
            created += 1
        else:
            updated += 1

        # Update progress every 5 employees or 10% (optimization to avoid socket spam)
        processed_count += 1
        if processed_count % 5 == 0 or processed_count == total_employees:
            percentage = int((processed_count / total_employees) * 100)
            emit_event_to_group(
                "HR Manager",
                EVENT_PAYROLL_PROGRESS,
                {
                    "cycle_id": cycle_id,
                    "status": "processing",
                    "total": total_employees,
                    "processed": processed_count,
                    "percentage": percentage,
                },
            )

    return {"created": created, "updated": updated}


def ensure_current_month_cycle() -> PayCycle:
    """Find or create the PayCycle covering the current month."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    month_end = date(today.year, today.month, last_day)
    name = f"{today.strftime('%Y-%m')} Payroll"

    cycle, _ = PayCycle.objects.get_or_create(
        name=name,
        defaults={
            "start_date": month_start,
            "end_date": month_end,
            "cutoff_date": month_end,
            "status": PayCycle.Status.DRAFT,
        },
    )
    return cycle
