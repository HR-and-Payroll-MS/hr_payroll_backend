from django.db.models.signals import post_save
from django.dispatch import receiver

from hr_payroll.expenses.models import ExpenseClaim
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.loans.models import LoanRequest
from hr_payroll.realtime.events import EVENT_NOTIFICATION
from hr_payroll.realtime.events import EVENT_REQUEST_CREATED
from hr_payroll.realtime.events import EVENT_REQUEST_UPDATE
from hr_payroll.realtime.socketio import emit_event_to_group
from hr_payroll.realtime.socketio import emit_event_to_user


def _notify_approvers(instance, request_type: str):
    """Notify HR Managers (and potentially line managers) of a new request."""
    # Simplified: Notify all HR Managers
    # Ideally, we would look up the specific Line Manager for the employee

    payload = {
        "id": instance.id,
        "type": request_type,
        "employee_name": str(instance.employee),
        "status": instance.status,
    }

    # Notify HR Group
    emit_event_to_group("HR Manager", EVENT_REQUEST_CREATED, payload)

    # Generic Notification (Toast)
    emit_event_to_group(
        "HR Manager",
        EVENT_NOTIFICATION,
        {
            "title": f"New {request_type}",
            "message": f"{instance.employee} submitted a {request_type}.",
            "type": "info",
        },
    )


def _notify_requester(instance, request_type: str):
    """Notify the requester of a status change."""
    if not instance.employee.user_id:
        return

    payload = {
        "id": instance.id,
        "type": request_type,
        "status": instance.status,
    }

    # Update Data (e.g., Table row)
    emit_event_to_user(instance.employee.user_id, EVENT_REQUEST_UPDATE, payload)

    # Generic Notification (Toast)
    emit_event_to_user(
        instance.employee.user_id,
        EVENT_NOTIFICATION,
        {
            "title": f"{request_type} Updated",
            "message": f"Your {request_type} is now {instance.status}.",
            "type": "success" if "approve" in instance.status.lower() else "info",
        },
    )


@receiver(post_save, sender=LeaveRequest)
def handle_leave_request(sender, instance: LeaveRequest, created: bool, **kwargs):  # noqa: FBT001
    if created:
        _notify_approvers(instance, "Leave Request")
    else:
        # Check if status field actually changed? (Skipping for now for simplicity, sends on every save)
        _notify_requester(instance, "Leave Request")


@receiver(post_save, sender=LoanRequest)
def handle_loan_request(sender, instance: LoanRequest, created: bool, **kwargs):  # noqa: FBT001
    if created:
        _notify_approvers(instance, "Loan Request")
    else:
        _notify_requester(instance, "Loan Request")


@receiver(post_save, sender=ExpenseClaim)
def handle_expense_claim(sender, instance: ExpenseClaim, created: bool, **kwargs):  # noqa: FBT001
    if created:
        _notify_approvers(instance, "Expense Claim")
    else:
        _notify_requester(instance, "Expense Claim")
