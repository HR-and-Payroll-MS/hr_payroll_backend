from django.contrib import admin

from hr_payroll.employees import models


@admin.register(models.Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "photo", "fingerprint_token", "time_zone"]
    search_fields = [
        "fingerprint_token",
        "time_zone",
        "office",
        "title",
        "employee_id",
        "health_care",
    ]
    list_filter = [
        "join_date",
        "last_working_date",
        "is_active",
        "created_at",
        "updated_at",
    ]


@admin.register(models.JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "effective_date", "job_title", "position_type"]
    search_fields = ["job_title", "position_type", "employment_type"]
    list_filter = ["effective_date", "employment_type"]


@admin.register(models.Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "employee",
        "contract_number",
        "contract_name",
        "contract_type",
    ]
    search_fields = ["contract_number", "contract_name", "contract_type"]
    list_filter = ["start_date", "end_date"]


@admin.register(models.EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "name", "file", "uploaded_at"]
    search_fields = ["name"]
    list_filter = ["uploaded_at", "created_at", "updated_at"]
