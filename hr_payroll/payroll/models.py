import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Compensation(models.Model):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="compensations"
    )
    total_compensation = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - representation
        return (
            f"Compensation(id={self.id}, employee_id={self.employee_id}, "
            f"total={self.total_compensation})"
        )

    def recalc_total(self) -> Decimal:
        total = sum((c.amount for c in self.components.all()), Decimal("0.00"))
        self.total_compensation = total
        self.save(update_fields=["total_compensation"])
        return total


class BankDetail(models.Model):
    """Bank details for direct deposit linked to an employee.

    Sensitive data should be handled carefully; this model stores plain fields
    but the project should enable encrypted fields in production if required.
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="bank_details"
    )
    bank_name = models.CharField(max_length=200)
    branch = models.CharField(max_length=200, blank=True)
    swift_bic = models.CharField(max_length=50, blank=True)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=100)
    iban = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"BankDetail({self.employee_id} {self.bank_name} {self.account_number})"


class Dependent(models.Model):
    """Tax/dependent information for an employee."""

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="dependents"
    )
    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"Dependent({self.employee_id} {self.name})"


class SalaryComponent(models.Model):
    class Kind(models.TextChoices):
        BASE = "base", "Base"
        RECURRING = "recurring", "Recurring"
        ONE_OFF = "one_off", "One-off"
        OFFSET = "offset", "Offset"

    compensation = models.ForeignKey(
        Compensation, on_delete=models.CASCADE, related_name="components"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    label = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - representation
        return (
            f"SalaryComponent(id={self.id}, compensation_id={self.compensation_id}, "
            f"kind={self.kind}, amount={self.amount}, label={self.label!r})"
        )


class PayrollCycle(models.Model):
    """A payroll cycle (e.g., monthly) with an optional eligibility list.

    - UUID primary key
    - Tracks the processing window (period_start/end) and cut-off dates
    - Maintains the person in charge for approvals
    - Supports either criteria 'all' or an explicit M2M list of employees
    """

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Bi-Weekly"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Eligibility(models.TextChoices):
        ALL = "all", "All Employees"
        LIST = "list", "Selected Employees"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    person_in_charge = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    period_start = models.DateField()
    period_end = models.DateField()
    cutoff_date = models.DateField()
    review_cutoff_date = models.DateField(null=True, blank=True)
    review_cutoff_enabled = models.BooleanField(default=False)
    eligibility_criteria = models.CharField(
        max_length=10, choices=Eligibility.choices, default=Eligibility.ALL
    )
    eligible_employees = models.ManyToManyField(
        "employees.Employee", blank=True, related_name="eligible_cycles"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover - representation
        # Use a standard hyphen to avoid ambiguous Unicode dash warnings
        return f"PayrollCycle({self.name} {self.period_start}-{self.period_end})"

    @property
    def days_in_period(self) -> int:
        return (self.period_end - self.period_start).days + 1


class PayrollRecord(models.Model):
    """A per-employee payslip for a given cycle.

    Uses UUID primary key and supports soft-delete via deleted_at.
    Numerical amounts are stored as Decimal in currency minor units.
    Attendance aggregates are stored as seconds for precision.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(
        PayrollCycle, on_delete=models.CASCADE, related_name="records"
    )
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="payroll_records"
    )

    # Components aligning to UI columns
    salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    actual = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    recurring = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    one_off = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    offset = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    ot = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_compensation = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Attendance integration (seconds for accurate arithmetic)
    period_start = models.DateField()
    period_end = models.DateField()
    actual_work_seconds = models.IntegerField(default=0)
    overtime_seconds = models.IntegerField(default=0)
    deficit_seconds = models.IntegerField(default=0)
    carry_over_overtime_seconds = models.IntegerField(default=0)

    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cycle__period_end", "employee_id", "-created_at"]
        unique_together = ("cycle", "employee")

    def __str__(self) -> str:  # pragma: no cover - representation
        e = getattr(self, "employee_id", None)
        c = getattr(self, "cycle_id", None)
        return f"PayrollRecord({e} @ {c})"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def recalc_total(self) -> Decimal:
        """Recompute the total compensation following the UI groups.

        Total = Salary + Actual + Recurring + One-off + OT - Offset
        (Assume offset is a deduction by convention.)
        """

        total = (
            (self.salary or 0)
            + (self.actual or 0)
            + (self.recurring or 0)
            + (self.one_off or 0)
            + (self.ot or 0)
            - (self.offset or 0)
        )
        # Coerce to Decimal to avoid type churn if fields are None
        if not isinstance(total, Decimal):
            total = Decimal(total)
        self.total_compensation = total
        self.save(update_fields=["total_compensation"])
        return total
