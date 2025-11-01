from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True, db_index=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=150, blank=True)
    budget_code = models.CharField(max_length=50, blank=True)
    manager = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_departments",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name
