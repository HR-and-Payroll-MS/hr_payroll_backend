from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def employee_photo_upload_to(instance: "Employee", filename: str) -> str:
    return f"employees/photos/{getattr(instance, 'pk', 'unknown')}/{filename}"


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        db_index=True,
    )
    photo = models.ImageField(upload_to=employee_photo_upload_to, null=True, blank=True)
    time_zone = models.CharField(max_length=50, blank=True)
    office = models.CharField(max_length=100, blank=True)
    # Employment benefit indicator moved from UserProfile
    health_care = models.CharField(max_length=100, blank=True)
    line_manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_employees",
    )
    title = models.CharField(max_length=150, blank=True, db_column="job_title")
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    join_date = models.DateField(null=True, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    last_working_date = models.DateField(null=True, blank=True)

    # Active flag maps to frontend status {ACTIVE, INACTIVE}
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Employee({self.user})"

    # Computed properties for service years
    @property
    def service_year(self) -> int:
        start = self.join_date or self.hire_date
        if not start:
            return 0
        today = timezone.now().date()
        years = (
            today.year
            - start.year
            - ((today.month, today.day) < (start.month, start.day))
        )
        return max(years, 0)

    @property
    def service_years(self) -> str:
        start = self.join_date or self.hire_date
        if not start:
            return ""
        today = timezone.now().date()
        months = (today.year - start.year) * 12 + (today.month - start.month)
        if today.day < start.day:
            months -= 1
        years, rem_months = divmod(max(months, 0), 12)
        parts = []
        if years:
            parts.append(f"{years} Year" + ("s" if years != 1 else ""))
        if rem_months:
            parts.append(f"{rem_months} Month" + ("s" if rem_months != 1 else ""))
        return " ".join(parts) or "0 Months"

    @property
    def full_name(self) -> str:
        name = getattr(self.user, "name", "").strip()
        if name:
            return name
        first = getattr(self.user, "first_name", "")
        last = getattr(self.user, "last_name", "")
        return f"{first} {last}".strip()

    @property
    def position(self) -> str:
        return self.title or ""

    @property
    def status(self) -> str:
        return "ACTIVE" if self.is_active else "INACTIVE"

    @property
    def email(self) -> str:
        return getattr(self.user, "email", "") or ""

    @property
    def phone(self) -> str:
        profile = getattr(self.user, "profile", None)
        return getattr(profile, "phone", "") if profile else ""


def employee_document_upload_to(instance: "EmployeeDocument", filename: str) -> str:
    emp_pk = getattr(getattr(instance, "employee", None), "pk", "unknown")
    return f"employees/{emp_pk}/{filename}"


# Backwards-compatibility for historic migrations referencing this symbol
def employee_upload_to(
    instance: "EmployeeDocument", filename: str
) -> str:  # pragma: no cover - migration shim
    return employee_document_upload_to(instance, filename)


class EmployeeDocument(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=employee_document_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    def clean(self):
        if self.file and hasattr(self.file, "size"):
            if self.file.size > 5 * 1024 * 1024:
                raise ValidationError({"file": "File too large (max 5MB)."})
        allowed_ext = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
        name = getattr(self.file, "name", "") or ""
        for ext in allowed_ext:
            if name.lower().endswith(ext):
                break
        else:
            raise ValidationError({"file": "Unsupported file type."})


class JobHistory(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="job_history"
    )
    effective_date = models.DateField()
    job_title = models.CharField(max_length=100)
    position_type = models.CharField(max_length=50, blank=True)

    class EmploymentType(models.TextChoices):
        FULLTIME = "fulltime", "Fulltime"
        PARTTIME = "parttime", "Part-time"
        CONTRACT = "contract", "Contract"

    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, blank=True
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

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.job_title} @ {self.effective_date}"


class Contract(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="contracts"
    )
    contract_number = models.CharField(max_length=50)
    contract_name = models.CharField(max_length=100)
    contract_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "pk"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.contract_name} ({self.contract_number})"
