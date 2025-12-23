import calendar
from datetime import date
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from hr_payroll.employees.models import Employee
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.policies import get_policy_document


def prorate_amount(base_salary: Decimal, worked_days: int, period_days: int) -> Decimal:
    """Prorate calculation used across the payroll module.

    Formula: (worked_days / period_days) * base_salary

    Notes:
    - If period_days is zero, returns 0.
    - Uses Decimal arithmetic and rounds to 2 decimal places.
    """
    if period_days <= 0:
        return Decimal("0.00")
    ratio = Decimal(worked_days) / Decimal(period_days)
    return (Decimal(base_salary) * ratio).quantize(Decimal("0.01"))


def _build_components_from_structure(emp: Employee):
    """Return base, earnings, deductions using the employee salary structure."""

    base_salary = Decimal("0.00")
    earnings: list[dict] = []
    deductions: list[dict] = []

    structure = getattr(emp, "salary_structure", None)
    if not structure:
        return base_salary, earnings, deductions

    base_salary = Decimal(structure.base_salary or 0)
    for item in structure.items.select_related("component"):
        comp = item.component
        if not comp:
            continue
        payload = {
            "label": comp.name,
            "amount": Decimal(item.amount),
            "component": comp,
        }
        if comp.component_type == comp.Type.DEDUCTION:
            deductions.append(payload)
        else:
            earnings.append(payload)

    return base_salary, earnings, deductions


def _fallback_components_from_policy() -> tuple[Decimal, list[dict], list[dict]]:
    """Mirror preview defaults when no salary structure exists."""

    policy = get_policy_document(org_id=1)
    salary_policy = (
        policy.get("salaryStructurePolicy", {}) if isinstance(policy, dict) else {}
    )
    base = Decimal(
        str(salary_policy.get("baseSalaryTemplate", {}).get("gradeA", 0) or 0)
    )

    allowance = (
        (base * Decimal("0.20")).quantize(Decimal("0.01")) if base else Decimal("0.00")
    )
    bonus = (
        (base * Decimal("0.05")).quantize(Decimal("0.01")) if base else Decimal("0.00")
    )

    earnings = [
        {"label": "Basic Salary", "amount": base, "component": None},
        {"label": "Allowance", "amount": allowance, "component": None},
        {"label": "Bonus", "amount": bonus, "component": None},
    ]

    gross_guess = sum(e["amount"] for e in earnings)
    tax = (gross_guess * Decimal("0.10")).quantize(Decimal("0.01"))
    pension = (gross_guess * Decimal("0.03")).quantize(Decimal("0.01"))
    deductions = [
        {"label": "Income Tax (10%)", "amount": tax, "component": None},
        {"label": "Pension (3%)", "amount": pension, "component": None},
    ]

    return base, earnings, deductions


@transaction.atomic
def generate_payroll_for_cycle(cycle_id: str) -> dict[str, int]:
    """Generate payroll slips aligned with the preview/upload flow."""

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

    for emp in employees.iterator():
        base_salary, earnings, deductions = _build_components_from_structure(emp)

        if base_salary <= 0 and not earnings and not deductions:
            base_salary, earnings, deductions = _fallback_components_from_policy()

        if base_salary > 0 and not any(e["label"] == "Basic Salary" for e in earnings):
            earnings = [
                {"label": "Basic Salary", "amount": base_salary, "component": None},
                *earnings,
            ]

        if not deductions:
            gross_guess = sum(e["amount"] for e in earnings)
            tax = (gross_guess * Decimal("0.10")).quantize(Decimal("0.01"))
            pension = (gross_guess * Decimal("0.03")).quantize(Decimal("0.01"))
            deductions = [
                {"label": "Income Tax (10%)", "amount": tax, "component": None},
                {"label": "Pension (3%)", "amount": pension, "component": None},
            ]

        total_earnings = sum(e["amount"] for e in earnings)
        total_deductions = sum(d["amount"] for d in deductions)
        net_pay = total_earnings - total_deductions

        slip, created_flag = PayrollSlip.objects.update_or_create(
            cycle=cycle,
            employee=emp,
            defaults={
                "base_salary": base_salary,
                "total_earnings": total_earnings,
                "total_deductions": total_deductions,
                "net_pay": net_pay,
                "total_work_duration": timedelta(0),
                "total_overtime_duration": timedelta(0),
                "total_deficit_duration": timedelta(0),
                "status": PayrollSlip.Status.DRAFT,
            },
        )

        # Replace line items with the latest breakdown
        slip.line_items.all().delete()

        for item in earnings:
            PayslipLineItem.objects.create(
                slip=slip,
                component=item.get("component"),
                label=item["label"],
                amount=item["amount"],
                category=PayslipLineItem.Category.RECURRING,
            )

        for item in deductions:
            category = (
                PayslipLineItem.Category.TAX
                if "tax" in item["label"].lower()
                else PayslipLineItem.Category.RECURRING
            )
            PayslipLineItem.objects.create(
                slip=slip,
                component=item.get("component"),
                label=item["label"],
                amount=item["amount"],
                category=category,
            )

        if created_flag:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated}


def ensure_current_month_cycle() -> PayCycle:
    """Find or create the PayCycle covering the current month.

    - Names the cycle as "<YYYY-MM> Payroll".
    - Sets start_date to first of month, end_date to last of month,
        cutoff_date=end_date.
    - Leaves manager_in_charge null and status as DRAFT.
    """

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
