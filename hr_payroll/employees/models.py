from django.conf import settings
from django.core.exceptions import ValidationError
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
    # Soft delete / active flag
    is_active = models.BooleanField(default=True)
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


# Position model removed: roles are represented via Employee.title only.


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        db_index=True,
    )
    # Keep code attribute name 'title' for backward compatibility;
    # align DB column to 'job_title' to match documentation.
    title = models.CharField(max_length=150, blank=True, db_column="job_title")
    hire_date = models.DateField(null=True, blank=True)
    supervisor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinates",
    )
    # Position removed; keep job title string for simplicity

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"
        RETIRED = "retired", "Retired"

    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    # Personal identity/contact fields moved to users.UserProfile
    # Soft delete / active flag
    is_active = models.BooleanField(default=True)
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        constraints = []

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Employee({self.user})"

    def save(self, *args, **kwargs):
        """Auto-sync is_active from employment_status.

        Per business rule: set is_active=False when employment_status is in
        {resigned, terminated, retired}; otherwise set True.
        """
        inactive_statuses = {
            self.EmploymentStatus.RESIGNED,
            self.EmploymentStatus.TERMINATED,
            self.EmploymentStatus.RETIRED,
        }
        self.is_active = self.employment_status not in inactive_statuses
        super().save(*args, **kwargs)


def employee_upload_to(instance: "EmployeeDocument", filename: str) -> str:
    emp_pk = getattr(getattr(instance, "employee", None), "pk", "unknown")
    return f"employees/{emp_pk}/{filename}"


class EmployeeDocument(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=employee_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    def clean(self):
        # Basic file validation: max 5MB, allowed extensions
        if self.file and hasattr(self.file, "size"):
            if self.file.size > 5 * 1024 * 1024:
                raise ValidationError({"file": "File too large (max 5MB)."})
        # Extension check
        allowed_ext = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
        name = getattr(self.file, "name", "") or ""
        for ext in allowed_ext:
            if name.lower().endswith(ext):
                break
        else:
            raise ValidationError({"file": "Unsupported file type."})
