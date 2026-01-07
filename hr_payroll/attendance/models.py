from __future__ import annotations

import ipaddress

from django.db import models
from django.utils import timezone


class OfficeNetworkRange(models.Model):
    """CIDR ranges that represent office networks for attendance gating."""

    name = models.CharField(max_length=100)
    cidr = models.CharField(max_length=64, help_text="CIDR, e.g. 192.168.0.0/24")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - simple
        return f"{self.name} ({self.cidr})"

    def contains(self, ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(
                self.cidr, strict=False
            )
        except ValueError:
            return False


class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("present", "Present"),
        ("absent", "Absent"),
        ("partial", "Partial"),
    )

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    shift_name = models.CharField(max_length=100, blank=True, default="")
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    clock_in_location = models.CharField(max_length=100, blank=True, default="")
    clock_out_location = models.CharField(max_length=100, blank=True, default="")
    paid_minutes = models.PositiveIntegerField(default=0)
    work_schedule_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        unique_together = ("employee", "date")

    def __str__(self) -> str:  # pragma: no cover - simple
        return f"Attendance({self.employee_id}:{self.date})"

    @property
    def paid_hours_display(self) -> str:
        hours = self.paid_minutes // 60
        mins = self.paid_minutes % 60
        return f"{hours}h{mins:02d}m"

    @property
    def work_schedule_hours_display(self) -> str:
        hours = self.work_schedule_minutes // 60
        mins = self.work_schedule_minutes % 60
        return f"{hours}h{mins:02d}m"


class AttendancePunch(models.Model):
    TYPE_CHECK_IN = "check_in"
    TYPE_CHECK_OUT = "check_out"
    TYPE_BREAK_START = "break_start"
    TYPE_BREAK_END = "break_end"

    TYPE_CHOICES = (
        (TYPE_CHECK_IN, "Check in"),
        (TYPE_CHECK_OUT, "Check out"),
        (TYPE_BREAK_START, "Break start"),
        (TYPE_BREAK_END, "Break end"),
    )

    attendance = models.ForeignKey(
        AttendanceRecord, on_delete=models.CASCADE, related_name="punches"
    )
    punch_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    location = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp", "id"]

    def __str__(self) -> str:  # pragma: no cover - simple
        return f"Punch({self.punch_type} @ {self.timestamp})"
