from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class LeaveType(models.Model):
    class Unit(models.TextChoices):
        DAYS = "Days", _("Days")
        HOURS = "Hours", _("Hours")

    name = models.CharField(
        max_length=100, unique=True, help_text=_("Engagement, Annual, Sick")
    )
    is_paid = models.BooleanField(default=True, help_text=_("Toggle: Paid / Unpaid"))
    unit = models.CharField(
        max_length=10,
        choices=Unit.choices,
        default=Unit.DAYS,
        help_text=_("Selection: Days or Hours"),
    )
    color_code = models.CharField(max_length=7, help_text=_("Hex Code (e.g., #00FF00)"))
    description = models.TextField(
        blank=True, default="", help_text=_("Optional description")
    )

    def __str__(self):
        return self.name


class LeavePolicy(models.Model):
    class AssignSchedule(models.TextChoices):
        ON_JOINING = "On Joining", _("On Joining")
        MANUAL = "Manual", _("Manual")

    class AccrualFrequency(models.TextChoices):
        YEARLY = "Yearly", _("Yearly")
        MONTHLY = "Monthly", _("Monthly")

    class GenderEligibility(models.TextChoices):
        ALL = "All", _("All")
        MALE = "Male", _("Male")
        FEMALE = "Female", _("Female")

    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.CASCADE, related_name="policies"
    )
    name = models.CharField(
        max_length=100, help_text=_("Policy Name (e.g., Senior Annual)")
    )
    description = models.TextField(help_text=_("Description input field"))
    assign_schedule = models.CharField(
        max_length=20, choices=AssignSchedule.choices, default=AssignSchedule.ON_JOINING
    )
    accrual_frequency = models.CharField(
        max_length=20, choices=AccrualFrequency.choices, default=AccrualFrequency.YEARLY
    )
    entitlement = models.DecimalField(
        max_digits=5, decimal_places=2, help_text=_("Entitlement (Days per year)")
    )
    max_carry_over = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, help_text=_("Maximum Carry Over")
    )
    carry_over_expire_month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text=_("Carry Over Expiration (Month)"),
    )
    carry_over_expire_day = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text=_("Carry Over Expiration (Day)"),
    )
    allow_hourly = models.BooleanField(
        default=False, help_text=_("Duration Allowed: Hourly toggle")
    )
    eligibility_gender = models.CharField(
        max_length=10,
        choices=GenderEligibility.choices,
        default=GenderEligibility.ALL,
        help_text=_("Eligibility"),
    )
    is_active = models.BooleanField(default=True, help_text=_("Toggle switch"))

    def __str__(self):
        return f"{self.name} ({self.leave_type.name})"

    def clean(self):
        # Basic validation for day/month
        if (
            self.carry_over_expire_month in [4, 6, 9, 11]
            and self.carry_over_expire_day > 30
        ):
            raise ValidationError(_("Invalid day for the selected month."))
        if self.carry_over_expire_month == 2:
            # Simplified leap year check (assuming 29 is max possible)
            if self.carry_over_expire_day > 29:
                raise ValidationError(_("February cannot have more than 29 days."))


class PublicHoliday(models.Model):
    name = models.CharField(
        max_length=100, help_text=_("Holiday Name (e.g., Eid Mubarak)")
    )
    start_date = models.DateField(help_text=_("From date"))
    end_date = models.DateField(help_text=_("To date"))
    year = models.IntegerField(help_text=_("Index for fast calendar filtering"))

    def __str__(self):
        return f"{self.name} ({self.year})"


class EmployeeBalance(models.Model):
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="leave_balances",
        help_text=_("The user who owns this balance"),
    )
    policy = models.ForeignKey(
        LeavePolicy,
        on_delete=models.CASCADE,
        related_name="balances",
        help_text=_("The rules governing this balance"),
    )
    entitled_days = models.DecimalField(
        max_digits=6, decimal_places=2, help_text=_("Total allowance")
    )
    used_days = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.00, help_text=_("Used days")
    )
    pending_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text=_("Days locked in Pending requests"),
    )
    carry_forward_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text=_("Days brought over from last year"),
    )

    class Meta:
        unique_together = ("employee", "policy")

    def __str__(self):
        return f"{self.employee} - {self.policy.name}"

    @property
    def available_days(self):
        return (self.entitled_days + self.carry_forward_days) - (
            self.used_days + self.pending_days
        )


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending", _("Pending")
        APPROVED = "Approved", _("Approved")
        REJECTED = "Rejected", _("Rejected")

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="leave_requests",
        help_text=_("Employee Name"),
    )
    policy = models.ForeignKey(
        LeavePolicy,
        on_delete=models.CASCADE,
        related_name="requests",
        help_text=_("Time Off Type dropdown"),
    )
    start_date = models.DateField(help_text=_("From / Select Date"))
    end_date = models.DateField(help_text=_("To / Select Date"))
    start_time = models.TimeField(
        null=True, blank=True, help_text=_("Used if allow_hourly is True")
    )
    end_time = models.TimeField(
        null=True, blank=True, help_text=_("Used if allow_hourly is True")
    )
    duration = models.DecimalField(
        max_digits=5, decimal_places=2, help_text=_("Total (e.g., 3 Days)")
    )
    notes = models.TextField(blank=True, default="", help_text=_("Note input field"))
    attachment = models.FileField(
        upload_to="leave_attachments/",
        null=True,
        blank=True,
        help_text=_("Upload attachment"),
    )
    assigned_approver = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_approvals",
        help_text=_("Assign To search field"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text=_("Status Badge"),
    )
    rejection_reason = models.TextField(
        blank=True, default="", help_text=_("If status is Rejected, reason why")
    )

    def __str__(self):
        return f"{self.employee} - {self.policy.name} ({self.start_date})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Start date cannot be after end date."))


class BalanceHistory(models.Model):
    class EventType(models.TextChoices):
        TAKEN = "Taken", _("Taken")
        ACCRUAL = "Accrual", _("Accrual")
        MANUAL_ADJUSTMENT = "Manual Adjustment", _("Manual Adjustment")

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="balance_history",
        help_text=_("The employee involved"),
    )
    policy = models.ForeignKey(
        LeavePolicy,
        on_delete=models.CASCADE,
        related_name="history",
        help_text=_("Type column"),
    )
    event_type = models.CharField(
        max_length=50, choices=EventType.choices, help_text=_("Event column")
    )
    date = models.DateField(help_text=_("Date column"))
    change_amount = models.DecimalField(
        max_digits=6, decimal_places=2, help_text=_("Change (Days) (+/- values)")
    )
    changed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        help_text=_("Changed By column"),
    )
    related_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_events",
        help_text=_("Links to the specific request"),
    )

    def __str__(self):
        return f"{self.employee} - {self.event_type} ({self.change_amount})"
