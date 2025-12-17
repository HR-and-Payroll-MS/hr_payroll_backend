from django.db import models


class OrganizationPolicy(models.Model):
    """Organization-wide policy document.

    This stores the canonical policy document (matching the frontend
    `initialPolicies` shape). For now, `org_id` is a simple integer identifier
    (frontend currently uses organizationId=1).
    """

    org_id = models.PositiveIntegerField(unique=True, default=1)
    document = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["org_id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"OrgPolicy(org_id={self.org_id})"


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
