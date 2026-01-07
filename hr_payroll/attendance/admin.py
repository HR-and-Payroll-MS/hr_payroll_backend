from django.contrib import admin

from hr_payroll.attendance.models import AttendancePunch
from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.attendance.models import OfficeNetworkRange


class AttendancePunchInline(admin.TabularInline):
    model = AttendancePunch
    extra = 0
    readonly_fields = ("punch_type", "timestamp", "location")
    can_delete = False
    ordering = ("timestamp", "id")


@admin.register(OfficeNetworkRange)
class OfficeNetworkRangeAdmin(admin.ModelAdmin):
    list_display = ("name", "cidr", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "cidr")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    inlines = [AttendancePunchInline]
    list_display = (
        "employee",
        "date",
        "status",
        "shift_name",
        "clock_in",
        "clock_out",
        "paid_minutes",
        "work_schedule_minutes",
    )
    list_filter = ("status", "date")
    search_fields = ("employee__user__username", "employee__employee_id", "shift_name")
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-date", "-id")


@admin.register(AttendancePunch)
class AttendancePunchAdmin(admin.ModelAdmin):
    list_display = ("attendance", "punch_type", "timestamp", "location")
    list_filter = ("punch_type",)
    search_fields = (
        "attendance__employee__user__username",
        "attendance__employee__employee_id",
        "location",
    )
    readonly_fields = ("created_at",)
    ordering = ("-timestamp", "-id")
