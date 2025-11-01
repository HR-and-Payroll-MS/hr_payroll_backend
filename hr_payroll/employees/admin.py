import csv

from django import forms
from django.contrib import admin
from django.contrib.admin.helpers import ActionForm
from django.http import HttpResponse

from hr_payroll.org.models import Department

from .models import Contract
from .models import Employee
from .models import EmployeeDocument
from .models import JobHistory


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "position", "department", "is_active")
    list_filter = ("is_active", "department")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "employee_id",
        "title",
    )
    actions = [
        "activate_selected",
        "deactivate_selected",
        "reassign_department",
        "export_as_csv",
    ]

    class EmployeeActionForm(ActionForm):
        department = forms.ModelChoiceField(
            queryset=Department.objects.all(), required=False
        )

    action_form = EmployeeActionForm

    @admin.action(description="Activate selected employees")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} employees.")

    @admin.action(description="Deactivate selected employees")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} employees.")

    @admin.action(description="Reassign department (uses action form field)")
    def reassign_department(self, request, queryset):
        dept_id = request.POST.get("department")
        if not dept_id:
            self.message_user(
                request,
                "Please select a department in the action form.",
                level="warning",
            )
            return
        try:
            dept = Department.objects.get(pk=dept_id)
        except Department.DoesNotExist:
            self.message_user(request, "Invalid department selected.", level="error")
            return
        updated = queryset.update(department=dept)
        self.message_user(request, f"Reassigned department for {updated} employees.")

    @admin.action(description="Export selected employees as CSV")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=employees.csv"
        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "username",
                "full_name",
                "email",
                "department",
                "title",
                "employee_id",
                "join_date",
                "status",
            ]
        )
        for e in queryset.select_related("user", "department"):
            writer.writerow(
                [
                    str(e.pk),
                    e.user.username,
                    e.full_name,
                    e.email,
                    e.department.name if e.department else "",
                    e.title,
                    e.employee_id,
                    e.join_date.isoformat() if e.join_date else "",
                    e.status,
                ]
            )
        return response


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = ("employee", "effective_date", "job_title", "employment_type")
    list_filter = ("employment_type",)
    search_fields = ("employee__user__username", "job_title")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "contract_number",
        "contract_name",
        "start_date",
        "end_date",
    )
    search_fields = ("contract_number", "contract_name")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("employee", "name", "uploaded_at")
    search_fields = ("name",)
