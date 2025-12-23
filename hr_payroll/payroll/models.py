"""
Payroll models with relational architecture.

This module implements a robust payroll system with master tables for banks
and salary components, employee-specific salary structures, and transactional
tables for pay cycles and payroll slips.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PayrollGeneralSetting(models.Model):
    """Global payroll configuration (singleton pattern)."""

    currency = models.CharField(
        max_length=3, default="USD", help_text=_("ISO Currency Code")
    )
    proration_policy = models.CharField(
        max_length=20,
        choices=[
            ("fixed_day", _("Fixed Day")),
            ("actual_days", _("Actual Days")),
        ],
        default="fixed_day",
        help_text=_("Proration policy for partial months"),
    )
    working_days_basis = models.IntegerField(
        default=20, help_text=_("Standard working days per month")
    )

    class Meta:
        verbose_name = _("Payroll General Setting")
        verbose_name_plural = _("Payroll General Settings")

    def __str__(self):
        return f"Payroll Settings ({self.currency})"

    def save(self, *args, **kwargs):
        # Ensure only one settings object exists (singleton pattern)
        self.pk = 1
        super().save(*args, **kwargs)


class BankMaster(models.Model):
    """
    Centralized bank registry.
    Prevents typos and standardizes bank information.
    """

    name = models.CharField(
        max_length=200, unique=True, help_text=_('Bank name (e.g., "Chase Bank")')
    )
    swift_code = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("SWIFT/BIC code for international transfers"),
    )
    code = models.CharField(
        max_length=50, blank=True, help_text=_("Local bank code or routing number")
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Bank Master")
        verbose_name_plural = _("Bank Masters")

    def __str__(self):
        return self.name


class SalaryComponent(models.Model):
    """
    Master list of salary components (earnings and deductions).
    e.g., "Basic Salary", "Transport", "Tax".
    """

    class Type(models.TextChoices):
        EARNING = "earning", _("Earning")
        DEDUCTION = "deduction", _("Deduction")

    name = models.CharField(
        max_length=100,
        help_text=_('Component name (e.g., "Basic Salary", "Transport Allowance")'),
    )
    component_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.EARNING,
        help_text=_("Type of component"),
    )
    is_taxable = models.BooleanField(
        default=True, help_text=_("Whether this component is subject to tax")
    )
    is_recurring = models.BooleanField(
        default=True, help_text=_("False for one-off payments like bonuses")
    )

    class Meta:
        ordering = ["component_type", "name"]
        verbose_name = _("Salary Component")
        verbose_name_plural = _("Salary Components")

    def __str__(self):
        return f"{self.name} ({self.component_type})"


class BankDetail(models.Model):
    """
    Employee bank account information.
    One-to-one with Employee, uses FK to BankMaster.
    """

    employee = models.OneToOneField(
        "employees.Employee", on_delete=models.CASCADE, related_name="bank_detail"
    )
    bank = models.ForeignKey(
        BankMaster, on_delete=models.PROTECT, help_text=_("Bank where account is held")
    )
    branch_name = models.CharField(
        max_length=200, blank=True, help_text=_("Specific branch location")
    )
    account_holder = models.CharField(
        max_length=200, help_text=_("Name on the account")
    )
    account_number = models.CharField(
        max_length=100, help_text=_("Bank account number")
    )
    iban = models.CharField(
        max_length=100, blank=True, help_text=_("International Bank Account Number")
    )

    class Meta:
        verbose_name = _("Bank Detail")
        verbose_name_plural = _("Bank Details")

    def __str__(self):
        return f"{self.employee} - {self.bank.name}"


class EmployeeSalaryStructure(models.Model):
    """
    Defines the employee's salary structure.
    Replaces old Compensation model.
    """

    employee = models.OneToOneField(
        "employees.Employee", on_delete=models.CASCADE, related_name="salary_structure"
    )
    base_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Base monthly salary"),
    )
    components = models.ManyToManyField(
        SalaryComponent, through="SalaryStructureItem", related_name="structures"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Employee Salary Structure")
        verbose_name_plural = _("Employee Salary Structures")

    def __str__(self):
        return f"Structure: {self.employee}"


class SalaryStructureItem(models.Model):
    """
    Through table for EmployeeSalaryStructure and SalaryComponent.
    Stores the specific amount for each component.
    """

    structure = models.ForeignKey(
        EmployeeSalaryStructure, on_delete=models.CASCADE, related_name="items"
    )
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text=_("Amount for this component")
    )

    class Meta:
        unique_together = ("structure", "component")
        verbose_name = _("Salary Structure Item")
        verbose_name_plural = _("Salary Structure Items")

    def __str__(self):
        return f"{self.structure.employee} - {self.component.name}: {self.amount}"


class Dependent(models.Model):
    """
    Employee dependents for insurance and tax purposes.
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="dependents"
    )
    name = models.CharField(max_length=200, help_text=_("Dependent's full name"))
    relationship = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Relationship (e.g., "Spouse", "Child")'),
    )
    date_of_birth = models.DateField(
        null=True, blank=True, help_text=_("Date of birth")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id", "name"]
        verbose_name = _("Dependent")
        verbose_name_plural = _("Dependents")

    def __str__(self):
        return f"{self.employee} - {self.name}"


class PayCycle(models.Model):
    """
    Represents a payroll cycle (e.g., monthly period).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PROCESSING = "processing", _("Processing")
        CLOSED = "closed", _("Closed")

    name = models.CharField(
        max_length=150, help_text=_('Cycle name (e.g., "January 2025")')
    )
    start_date = models.DateField(help_text=_("Cycle start date"))
    end_date = models.DateField(help_text=_("Cycle end date"))
    cutoff_date = models.DateField(help_text=_("Cut-off date for processing"))
    manager_in_charge = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_cycles",
        help_text=_("Manager responsible for this cycle"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text=_("Cycle status"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-end_date", "-created_at"]
        verbose_name = _("Pay Cycle")
        verbose_name_plural = _("Pay Cycles")

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"


class PayrollSlip(models.Model):
    """
    A payroll slip for an employee in a specific cycle.
    Snapshot of salary structure + attendance data.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PAID = "paid", _("Paid")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(PayCycle, on_delete=models.CASCADE, related_name="slips")
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="payslips"
    )

    # Financial snapshots
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, help_text=_("Base salary snapshot")
    )
    total_earnings = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Total earnings"),
    )
    total_deductions = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Total deductions"),
    )
    net_pay = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Net pay (earnings - deductions)"),
    )

    # Attendance integration (using DurationField)
    total_work_duration = models.DurationField(
        default=timedelta(0), help_text=_("Total work time")
    )
    total_overtime_duration = models.DurationField(
        default=timedelta(0), help_text=_("Total overtime")
    )
    total_deficit_duration = models.DurationField(
        default=timedelta(0), help_text=_("Total deficit time")
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text=_("Slip status"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("cycle", "employee")
        ordering = ["-cycle__end_date", "employee_id", "-created_at"]
        verbose_name = _("Payroll Slip")
        verbose_name_plural = _("Payroll Slips")

    def __str__(self):
        return f"{self.employee} - {self.cycle.name}"


class PayslipLineItem(models.Model):
    """
    Individual line items on a payroll slip.
    e.g., recurring allowance, one-off bonus, overtime pay.
    """

    class Category(models.TextChoices):
        RECURRING = "recurring", _("Recurring")
        ONE_OFF = "one_off", _("One-off")
        OVERTIME = "overtime", _("Overtime")
        TAX = "tax", _("Tax")

    slip = models.ForeignKey(
        PayrollSlip, on_delete=models.CASCADE, related_name="line_items"
    )
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Reference to salary component"),
    )
    label = models.CharField(
        max_length=100, help_text=_('Display label (e.g., "Overtime (10 hours)")')
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text=_("Line item amount")
    )
    category = models.CharField(
        max_length=20, choices=Category.choices, help_text=_("Category for grouping")
    )

    class Meta:
        ordering = ["slip", "category", "id"]
        verbose_name = _("Payslip Line Item")
        verbose_name_plural = _("Payslip Line Items")

    def __str__(self):
        return f"{self.slip.employee} - {self.label}"


class PayslipDocument(models.Model):
    """Stored payslip PDF uploaded after preview/generation."""

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="payslip_documents"
    )
    cycle = models.ForeignKey(
        PayCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payslip_documents",
    )
    month = models.CharField(
        max_length=7,
        blank=True,
        help_text=_("Payroll month in YYYY-MM format (from preview/upload)"),
    )
    file = models.FileField(upload_to="payslips/")
    gross = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Gross amount from the generated slip"),
    )
    net = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Net amount from the generated slip"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_payslip_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = _("Payslip Document")
        verbose_name_plural = _("Payslip Documents")

    def __str__(self):
        return f"Payslip {self.month or ''} - {self.employee}"
