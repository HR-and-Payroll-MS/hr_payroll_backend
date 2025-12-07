from django.contrib import admin

from hr_payroll.attendance import models


@admin.register(models.Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "date", "clock_in", "clock_in_location"]
    search_fields = ["clock_in_location", "clock_out_location", "notes", "status"]
    list_filter = [
        "date",
        "clock_in",
        "clock_out",
        "status",
        "created_at",
        "updated_at",
    ]


@admin.register(models.AttendanceAdjustment)
class AttendanceAdjustmentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "attendance",
        "performed_by",
        "previous_paid_time",
        "new_paid_time",
    ]
    search_fields = ["notes"]
    list_filter = ["created_at"]


@admin.register(models.OfficeNetwork)
class OfficeNetworkAdmin(admin.ModelAdmin):
    list_display = ["id", "label", "cidr", "is_active", "created_at"]
    search_fields = ["label", "cidr"]
    list_filter = ["is_active", "created_at"]
