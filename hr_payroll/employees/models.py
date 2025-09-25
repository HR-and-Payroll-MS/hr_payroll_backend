from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    title = models.CharField(max_length=150, blank=True)
    hire_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Employee({self.user})"


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
