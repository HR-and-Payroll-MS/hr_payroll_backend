from django.contrib import admin

from hr_payroll.org import models


@admin.register(models.Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "description", "location", "budget_code"]
    search_fields = ["name", "description", "location", "budget_code"]
    list_filter = ["is_active", "created_at", "updated_at"]
