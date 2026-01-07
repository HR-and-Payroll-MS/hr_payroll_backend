from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from hr_payroll.employees.models import Employee


class ExpenseRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        REIMBURSED = "reimbursed", _("Reimbursed")

    class Category(models.TextChoices):
        TRAVEL = "travel", _("Travel")
        MEALS = "meals", _("Meals")
        ACCOMMODATION = "accommodation", _("Accommodation")
        SUPPLIES = "supplies", _("Office Supplies")
        OTHER = "other", _("Other")

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="expenses"
    )
    category = models.CharField(
        max_length=30, choices=Category.choices, default=Category.OTHER
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    receipt = models.FileField(upload_to="expense_receipts/", null=True, blank=True)
    expense_date = models.DateField()

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    # Approval
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_expenses",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    payroll_slip = models.ForeignKey(
        "payroll.PayrollSlip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reimbursed_expenses",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Expense {self.id}: {self.employee} - {self.category} - {self.amount}"
