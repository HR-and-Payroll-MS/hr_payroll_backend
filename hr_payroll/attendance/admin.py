from django.contrib import admin

from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment
from hr_payroll.attendance.models import OfficeNetwork


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "employee",
        "clock_in",
        "clock_out",
        "work_schedule_hours",
        "paid_time",
        "status",
        "overtime_seconds",
    )
    list_filter = (
        "status",
        "date",
        "employee__department",
        "employee__office",
    )
    search_fields = (
        "employee__user__username",
        "employee__user__first_name",
        "employee__user__last_name",
        "employee__employee_id",
        "clock_in_location",
        "clock_out_location",
        "notes",
    )
    autocomplete_fields = ("employee",)
    ordering = ("-date",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "employee",
                    "date",
                    "status",
                )
            },
        ),
        (
            "Clock times",
            {
                "fields": (
                    "clock_in",
                    "clock_in_location",
                    "clock_out",
                    "clock_out_location",
                )
            },
        ),
        (
            "Payroll",
            {"fields": ("work_schedule_hours", "paid_time", "overtime_seconds")},
        ),
        ("Meta", {"fields": ("notes", "created_at", "updated_at")}),
    )

    actions = ("mark_approved",)

    @admin.action(description="Mark selected as approved")
    def mark_approved(self, request, queryset):
        queryset.update(status=Attendance.Status.APPROVED)


@admin.register(AttendanceAdjustment)
class AttendanceAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "attendance",
        "performed_by",
        "previous_paid_time",
        "new_paid_time",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "attendance__employee__user__username",
        "attendance__employee__employee_id",
        "performed_by__username",
        "notes",
    )
    autocomplete_fields = ("attendance", "performed_by")
    ordering = ("-created_at",)


@admin.register(OfficeNetwork)
class OfficeNetworkAdmin(admin.ModelAdmin):
    list_display = ("label", "cidr", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("label", "cidr")
    ordering = ("cidr",)
    actions = ("activate_selected", "deactivate_selected")

    @admin.action(description="Activate selected networks")
    def activate_selected(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected networks")
    def deactivate_selected(self, request, queryset):
        queryset.update(is_active=False)
