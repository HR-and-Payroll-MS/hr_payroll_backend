from django.contrib import admin

from hr_payroll.leaves import models


@admin.register(models.LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "is_paid", "unit", "color_code"]
    search_fields = ["name", "unit", "color_code", "description"]
    list_filter = ["is_paid", "unit"]


@admin.register(models.LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ["id", "leave_type", "name", "description", "assign_schedule"]
    search_fields = [
        "name",
        "description",
        "assign_schedule",
        "accrual_frequency",
        "eligibility_gender",
    ]
    list_filter = [
        "assign_schedule",
        "accrual_frequency",
        "allow_hourly",
        "eligibility_gender",
        "is_active",
    ]


@admin.register(models.PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "start_date", "end_date", "year"]
    search_fields = ["name"]
    list_filter = ["start_date", "end_date"]


@admin.register(models.EmployeeBalance)
class EmployeeBalanceAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "policy", "entitled_days", "used_days"]


@admin.register(models.LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "policy", "start_date", "end_date"]
    search_fields = ["notes", "status", "rejection_reason"]
    list_filter = ["start_date", "end_date", "status"]


@admin.register(models.BalanceHistory)
class BalanceHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "policy", "event_type", "date"]
    search_fields = ["event_type"]
    list_filter = ["event_type", "date"]
