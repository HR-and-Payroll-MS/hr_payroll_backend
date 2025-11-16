from django.conf import settings
from django.db import models
from django.utils import timezone


def employee_photo_upload_to(
    instance, filename
):  # pragma: no cover - path logic trivial
    return f"employees/photos/{instance.pk}/{filename}"


def employee_document_upload_to(
    instance, filename
):  # pragma: no cover - path logic trivial
    return f"employees/documents/{instance.employee_id}/{filename}"


# Backward-compat alias for historical migration 0002
def employee_upload_to(instance, filename):  # pragma: no cover - for migrations
    return employee_document_upload_to(instance, filename)


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee"
    )
    photo = models.ImageField(upload_to=employee_photo_upload_to, blank=True, null=True)
    # Simple token alias to map a device-submitted fingerprint/template to an employee
    # Can store hashed template IDs or external device identifiers
    fingerprint_token = models.CharField(
        max_length=128, unique=True, blank=True, null=True
    )
    time_zone = models.CharField(max_length=50, blank=True)
    office = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=150, blank=True)
    employee_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    join_date = models.DateField(blank=True, null=True)
    last_working_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    line_manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_employees",
    )
    health_care = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):  # pragma: no cover - trivial
        return f"Employee({self.user.username})"

    @property
    def service_years(self):  # pragma: no cover - simple date math
        if not self.join_date:
            return ""
        today = timezone.localdate()
        delta = today - self.join_date
        years = delta.days // 365
        return f"{years}"


class JobHistory(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="job_history"
    )
    effective_date = models.DateField()
    job_title = models.CharField(max_length=100)
    position_type = models.CharField(max_length=50, blank=True)
    employment_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("fulltime", "Fulltime"),
            ("parttime", "Part-time"),
            ("contract", "Contract"),
        ],
    )
    line_manager = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="line_managed_histories",
    )

    class Meta:
        ordering = ["effective_date", "pk"]

    def __str__(self):  # pragma: no cover
        return f"JobHistory({self.employee_id}:{self.job_title})"


class Contract(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="contracts"
    )
    contract_number = models.CharField(max_length=50)
    contract_name = models.CharField(max_length=100)
    contract_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["start_date", "pk"]

    def __str__(self):  # pragma: no cover
        return f"Contract({self.contract_number})"


class EmployeeDocument(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="documents"
    )
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=employee_document_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):  # pragma: no cover
        return f"EmployeeDocument({self.name})"
