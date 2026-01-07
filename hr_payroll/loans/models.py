from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from hr_payroll.employees.models import Employee


class LoanRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        ACTIVE = "active", _("Active (Disbursed)")
        CLOSED = "closed", _("Closed (Paid)")

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="loans"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text=_("Requested Amount")
    )
    term_months = models.PositiveIntegerField(help_text=_("Repayment period in months"))
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text=_("Interest rate % applied at time of request"),
    )
    monthly_installment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Calculated monthly deduction"),
    )
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    # Approval Workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_loans",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Loan {self.id}: {self.employee} - {self.amount}"


class LoanRepayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Deducted/Paid")
        SKIPPED = "skipped", _("Skipped")

    loan = models.ForeignKey(
        LoanRequest, on_delete=models.CASCADE, related_name="repayments"
    )
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Link to Payroll when deducted
    payroll_slip = models.ForeignKey(
        "payroll.PayrollSlip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_repayments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"Repayment {self.due_date} - {self.amount}"
