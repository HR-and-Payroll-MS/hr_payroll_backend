import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Attendance(models.Model):
    """Core attendance record.

    - UUID PK
    - One record per date/shift per employee
    - Computed properties: logged_time, deficit
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    date = models.DateField()
    clock_in = models.DateTimeField()
    clock_in_location = models.CharField(max_length=255)
    clock_out = models.DateTimeField(null=True, blank=True)
    clock_out_location = models.CharField(max_length=255, blank=True, default="")
    work_schedule_hours = models.IntegerField(default=8)
    paid_time = models.DurationField(default=timedelta(0))
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    # Denormalized cache for daily overtime/deficit in seconds.
    # Positive => overtime, Negative => deficit, 0 => exactly scheduled.
    overtime_seconds = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        unique_together = (("employee", "date"),)

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"Attendance({self.employee_id}@{self.date})"

    @property
    def logged_time(self):
        """Compute raw logged time (clock_out - clock_in) when clock_out is present."""
        if not self.clock_out:
            return None
        return self.clock_out - self.clock_in

    @property
    def deficit(self):
        """Compute schedule - paid_time (positive = deficit, negative = overtime)."""
        scheduled = timezone.timedelta(hours=int(self.work_schedule_hours))
        paid = self.paid_time or timezone.timedelta(0)
        return scheduled - paid

    @property
    def overtime(self):
        """Paid time minus scheduled time (positive = overtime, negative = deficit)."""
        d = self.deficit
        if d is None:
            return None
        seconds = -int(d.total_seconds())
        return timezone.timedelta(seconds=seconds)


class AttendanceAdjustment(models.Model):
    """Audit trail for adjustments to paid_time or attendance details."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance = models.ForeignKey(
        Attendance, on_delete=models.CASCADE, related_name="adjustments"
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    previous_paid_time = models.DurationField(null=True, blank=True)
    new_paid_time = models.DurationField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"AttendanceAdjustment({self.attendance_id} by {self.performed_by_id})"
