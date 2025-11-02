from decimal import Decimal

from django.db import models


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
