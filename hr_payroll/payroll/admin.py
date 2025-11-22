from django.contrib import admin

from .models import BankDetail
from .models import BankMaster
from .models import Dependent
from .models import EmployeeSalaryStructure
from .models import PayCycle
from .models import PayrollGeneralSetting
from .models import PayrollSlip
from .models import PayslipLineItem
from .models import SalaryComponent
from .models import SalaryStructureItem


@admin.register(BankMaster)
class BankMasterAdmin(admin.ModelAdmin):
    list_display = ("name", "swift_code", "code")
    search_fields = ("name", "swift_code", "code")
    ordering = ("name",)


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ("name", "component_type", "is_taxable", "is_recurring")
    list_filter = ("component_type", "is_taxable", "is_recurring")
    search_fields = ("name",)
    ordering = ("component_type", "name")


@admin.register(PayrollGeneralSetting)
class PayrollGeneralSettingAdmin(admin.ModelAdmin):
    list_display = ("currency", "proration_policy", "working_days_basis")

    def has_add_permission(self, request):
        # Singleton - only one settings object
        return not PayrollGeneralSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of the settings object
        return False


@admin.register(EmployeeSalaryStructure)
class EmployeeSalaryStructureAdmin(admin.ModelAdmin):
    list_display = ("employee", "base_salary", "updated_at")
    search_fields = ("employee__user__username", "employee__user__email")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("employee",)


@admin.register(BankDetail)
class BankDetailAdmin(admin.ModelAdmin):
    list_display = ("employee", "bank", "account_number")
    search_fields = ("employee__user__username", "account_number")
    autocomplete_fields = ("employee", "bank")


@admin.register(Dependent)
class DependentAdmin(admin.ModelAdmin):
    list_display = ("employee", "name", "relationship", "date_of_birth")
    search_fields = ("employee__user__username", "name")
    autocomplete_fields = ("employee",)


@admin.register(PayCycle)
class PayCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "cutoff_date", "status")
    list_filter = ("status",)
    search_fields = ("name",)
    date_hierarchy = "start_date"
    autocomplete_fields = ("manager_in_charge",)


@admin.register(PayrollSlip)
class PayrollSlipAdmin(admin.ModelAdmin):
    list_display = ("employee", "cycle", "base_salary", "net_pay", "status")
    list_filter = ("status", "cycle")
    search_fields = ("employee__user__username",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("employee", "cycle")


@admin.register(PayslipLineItem)
class PayslipLineItemAdmin(admin.ModelAdmin):
    list_display = ("slip", "label", "amount", "category")
    list_filter = ("category",)
    search_fields = ("label",)
    autocomplete_fields = ("slip", "component")


@admin.register(SalaryStructureItem)
class SalaryStructureItemAdmin(admin.ModelAdmin):
    list_display = ("structure", "component", "amount")
    autocomplete_fields = ("structure", "component")
