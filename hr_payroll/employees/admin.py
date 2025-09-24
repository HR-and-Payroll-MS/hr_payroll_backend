from django.contrib import admin

from .models import Department, Employee, EmployeeDocument


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name", "description")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "title")
    list_filter = ("department",)
    search_fields = ("user__username", "user__email", "title")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("employee", "name", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("name", "employee__user__username")
