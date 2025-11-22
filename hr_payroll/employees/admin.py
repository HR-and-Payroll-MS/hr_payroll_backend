import csv

from django.contrib import admin
from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpResponse
from django.utils.html import format_html

from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure

from .models import Contract
from .models import Employee
from .models import EmployeeDocument
from .models import JobHistory


class JobHistoryInline(admin.TabularInline):
    model = JobHistory
    extra = 1
    fields = (
        "effective_date",
        "job_title",
        "position_type",
        "employment_type",
        "line_manager",
    )
    autocomplete_fields = ("line_manager",)
    fk_name = "employee"


class ContractInline(admin.TabularInline):
    model = Contract
    extra = 0
    fields = (
        "contract_number",
        "contract_name",
        "contract_type",
        "start_date",
        "end_date",
    )
    classes = ("collapse",)


class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 0
    fields = ("name", "file", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class DependentInline(admin.TabularInline):
    model = Dependent
    extra = 0
    fields = ("name", "relationship", "date_of_birth")


class BankDetailInline(admin.TabularInline):
    model = BankDetail
    extra = 0
    fields = (
        "bank",
        "branch_name",
        "account_holder",
        "account_number",
        "iban",
    )
    autocomplete_fields = ("bank",)


class SalaryStructureInline(admin.TabularInline):
    model = EmployeeSalaryStructure
    extra = 0
    fields = ("base_salary", "updated_at")
    readonly_fields = ("updated_at",)
    can_delete = True
    show_change_link = True


class HasLineManagerFilter(admin.SimpleListFilter):
    title = "has line manager"
    parameter_name = "has_lm"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "yes":
            return queryset.exclude(line_manager__isnull=True)
        if val == "no":
            return queryset.filter(line_manager__isnull=True)
        return queryset


class IsDeptManagerFilter(admin.SimpleListFilter):
    title = "is department manager"
    parameter_name = "is_dept_mgr"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "yes":
            return queryset.filter(managed_departments__isnull=False).distinct()
        if val == "no":
            return queryset.filter(managed_departments__isnull=True)
        return queryset


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "photo_thumb",
        "employee_id",
        "username",
        "full_name",
        "email",
        "department_name",
        "title",
        "status",
        "service_years",
        "join_date",
    )
    list_filter = (
        "is_active",
        "department",
        HasLineManagerFilter,
        IsDeptManagerFilter,
        "join_date",
    )
    search_fields = (
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "title",
        "office",
    )
    readonly_fields = ("employee_id", "created_at", "updated_at", "photo_preview")
    fieldsets = (
        (
            "Identity",
            {
                "fields": ("user", "employee_id", "photo", "photo_preview"),
                "description": (
                    "Link the employee to a user account and upload a profile photo."
                ),
            },
        ),
        (
            "Organization",
            {
                "fields": ("department", "line_manager", "office", "time_zone"),
                "classes": ("collapse",),
            },
        ),
        (
            "Role",
            {
                "fields": (
                    "title",
                    "health_care",
                    "join_date",
                    "last_working_date",
                    "is_active",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )
    inlines = [
        JobHistoryInline,
        ContractInline,
        DependentInline,
        BankDetailInline,
        EmployeeDocumentInline,
        SalaryStructureInline,
    ]
    autocomplete_fields = ("user", "department", "line_manager")
    list_select_related = ("user", "department", "line_manager")
    date_hierarchy = "join_date"
    save_on_top = True
    actions = (
        "activate_selected",
        "deactivate_selected",
        "send_welcome_email",
        "export_csv",
        "recalc_compensations",
    )

    # Display helpers
    def username(self, obj):
        return obj.user.username

    def email(self, obj):
        return obj.user.email

    def full_name(self, obj):
        return obj.user.name

    def department_name(self, obj):
        return getattr(obj.department, "name", "")

    def status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    @admin.display(description="Photo")
    def photo_thumb(self, obj):
        if obj.photo:
            return format_html(
                (
                    '<img src="{}" style="height:32px;width:32px;'
                    'border-radius:50%;object-fit:cover;"/>'
                ),
                obj.photo.url,
            )
        return ""

    @admin.display(description="Preview")
    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                (
                    '<img src="{}" style="max-height:160px;'
                    'border:1px solid #ddd;padding:4px;border-radius:6px;"/>'
                ),
                obj.photo.url,
            )
        return ""

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "department", "line_manager")
        )

    # Bulk actions
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request, f"Activated {updated} employees", level=messages.SUCCESS
        )

    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request, f"Deactivated {updated} employees", level=messages.WARNING
        )

    def send_welcome_email(self, request, queryset):
        count = 0
        for emp in queryset.select_related("user"):
            if emp.user.email:
                msg = (
                    f"Hi {emp.user.first_name or emp.user.username}, "
                    "your employee profile is now active."
                )
                send_mail(
                    subject="Welcome to HR & Payroll",
                    message=msg,
                    from_email=None,
                    recipient_list=[emp.user.email],
                    fail_silently=True,
                )
                count += 1
        self.message_user(
            request, f"Queued welcome email for {count} employees", level=messages.INFO
        )

    def recalc_compensations(self, request, queryset):
        # TODO: Update for new salary structure model
        self.message_user(
            request,
            "Recalculation feature needs to be updated for new salary structure",
            level=messages.WARNING,
        )

    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=employees.csv"
        writer = csv.writer(response)
        writer.writerow(
            [
                "Employee ID",
                "Username",
                "Email",
                "Full Name",
                "Department",
                "Title",
                "Office",
                "Join Date",
                "Status",
            ]
        )
        for e in queryset.select_related("user", "department"):
            writer.writerow(
                [
                    e.employee_id or "",
                    e.user.username,
                    e.user.email,
                    e.user.name,
                    getattr(e.department, "name", ""),
                    e.title,
                    e.office,
                    e.join_date or "",
                    "Active" if e.is_active else "Inactive",
                ]
            )
        return response


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "effective_date",
        "job_title",
        "position_type",
        "employment_type",
    )
    list_filter = ("employment_type", "position_type", "effective_date")
    search_fields = ("employee__user__username", "job_title")
    date_hierarchy = "effective_date"


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "contract_number",
        "contract_name",
        "contract_type",
        "start_date",
        "end_date",
    )
    list_filter = ("contract_type", "start_date")
    search_fields = ("contract_number", "contract_name", "employee__user__username")
    date_hierarchy = "start_date"


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("employee", "name", "uploaded_at", "preview_link")
    search_fields = ("name", "employee__user__username")
    list_filter = ("uploaded_at",)
    readonly_fields = ("uploaded_at", "created_at", "updated_at")

    @admin.display(description="File")
    def preview_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Open</a>', obj.file.url)
        return ""
