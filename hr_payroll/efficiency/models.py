from django.db import models


class EfficiencyTemplate(models.Model):
    """Dynamic efficiency template created by HR.

    Stores the full JSON schema used by the frontend form builder.
    Optionally scoped to an organization (org_id) and/or department.
    """

    org_id = models.PositiveIntegerField(default=1)
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="efficiency_templates",
    )
    title = models.CharField(max_length=255)
    schema = models.JSONField(default=dict)
    version = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_efficiency_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"EfficiencyTemplate({self.id}:{self.title})"


class EfficiencyEvaluation(models.Model):
    """Per-employee evaluation submission by Line Managers.

    Stores evaluator, target employee, department, and computed summary.
    The full payload (answers/report) is kept in JSON `data` for auditing.
    """

    template = models.ForeignKey(
        EfficiencyTemplate, on_delete=models.CASCADE, related_name="evaluations"
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="efficiency_evaluations",
    )
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="efficiency_evaluations",
    )
    evaluator = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="efficiency_evaluated",
    )
    data = models.JSONField(default=dict)
    total_achieved = models.FloatField(default=0)
    total_possible = models.FloatField(default=0)
    total_efficiency = models.FloatField(default=0)
    status = models.CharField(
        max_length=20,
        default="submitted",
        choices=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            "EfficiencyEvaluation("
            f"emp={self.employee_id}, tpl={self.template_id}, "
            f"eff={self.total_efficiency})"
        )
