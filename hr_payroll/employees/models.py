from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
    # Profile / display fields
    photo = models.ImageField(upload_to="employees/photos/", null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=100, blank=True)

    # Separate status badge for UI; independent from employment_status below
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    time_zone = models.CharField(max_length=50, blank=True)
    office = models.CharField(max_length=100, blank=True)
    line_manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_employees",
    )
    # Keep code attribute name 'title' for backward compatibility;
    # align DB column to 'job_title' to match documentation.
    title = models.CharField(max_length=150, blank=True, db_column="job_title")
    hire_date = models.DateField(null=True, blank=True)
    # Identifiers and dates used by new UI
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    join_date = models.DateField(null=True, blank=True)
    supervisor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinates",
    )
    # Position removed; keep job title string for simplicity

    # General editable personal info fields (kept on Employee per spec)
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    email_address = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    health_care = models.CharField(max_length=100, blank=True)

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Single"
        MARRIED = "married", "Married"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"

    marital_status = models.CharField(
        max_length=20, choices=MaritalStatus.choices, blank=True
    )
    personal_tax_id = models.CharField(max_length=50, blank=True)
    social_insurance = models.CharField(max_length=100, blank=True)

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

    # Computed properties for service years
    @property
    def service_year(self) -> int:
        """Whole years of service based on join_date or hire_date."""
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
        """Human readable service duration, e.g., '3 Years 7 Months'."""
        start = self.join_date or self.hire_date
        if not start:
            return ""
        today = timezone.now().date()
        # compute months diff
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
