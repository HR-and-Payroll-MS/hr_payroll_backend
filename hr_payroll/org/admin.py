from django.contrib import admin

from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "budget_code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "location", "budget_code")
