from celery import shared_task

from hr_payroll.payroll.services import ensure_current_month_cycle
from hr_payroll.payroll.services import generate_payroll_for_cycle


@shared_task(name="payroll.run_cycle")
def run_cycle_task(cycle_id: str) -> dict:
    """Celery task wrapper to run payroll generation for a cycle."""
    return generate_payroll_for_cycle(cycle_id)


@shared_task(name="payroll.run_current_month_cycle")
def run_current_month_cycle_task() -> dict:
    """Find or create the current month's PayCycle and generate payroll."""

    cycle = ensure_current_month_cycle()
    return generate_payroll_for_cycle(str(cycle.pk))
