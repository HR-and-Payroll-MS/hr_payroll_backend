from django.contrib import admin

from hr_payroll.payroll import models


@admin.register(models.PayrollGeneralSetting)
class PayrollGeneralSettingAdmin(admin.ModelAdmin):
    list_display = ["id", "currency", "proration_policy", "working_days_basis"]
    search_fields = ["currency", "proration_policy"]
    list_filter = ["proration_policy"]


@admin.register(models.BankMaster)
class BankMasterAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "swift_code", "code"]
    search_fields = ["name", "swift_code", "code"]


@admin.register(models.SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "component_type", "is_taxable", "is_recurring"]
    search_fields = ["name", "component_type"]
    list_filter = ["component_type", "is_taxable", "is_recurring"]


@admin.register(models.BankDetail)
class BankDetailAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "bank", "branch_name", "account_holder"]
    search_fields = ["branch_name", "account_holder", "account_number", "iban"]


@admin.register(models.EmployeeSalaryStructure)
class EmployeeSalaryStructureAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "base_salary", "updated_at"]
    list_filter = ["updated_at"]


@admin.register(models.SalaryStructureItem)
class SalaryStructureItemAdmin(admin.ModelAdmin):
    list_display = ["id", "structure", "component", "amount"]


@admin.register(models.Dependent)
class DependentAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "name", "relationship", "date_of_birth"]
    search_fields = ["name", "relationship"]
    list_filter = ["date_of_birth", "created_at", "updated_at"]


@admin.register(models.PayCycle)
class PayCycleAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "start_date", "end_date", "cutoff_date"]
    search_fields = ["name", "status"]
    list_filter = [
        "start_date",
        "end_date",
        "cutoff_date",
        "status",
        "created_at",
        "updated_at",
    ]


@admin.register(models.PayrollSlip)
class PayrollSlipAdmin(admin.ModelAdmin):
    list_display = ["id", "cycle", "employee", "base_salary", "total_earnings"]
    search_fields = ["status"]
    list_filter = ["status", "created_at", "updated_at"]


@admin.register(models.PayslipLineItem)
class PayslipLineItemAdmin(admin.ModelAdmin):
    list_display = ["id", "slip", "component", "label", "amount"]
    search_fields = ["label", "category"]
    list_filter = ["category"]


@admin.register(models.PayslipDocument)
class PayslipDocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "employee", "month", "cycle", "uploaded_by", "uploaded_at"]
    search_fields = ["employee__user__username", "employee__user__email", "month"]
    list_filter = ["month", "cycle", "uploaded_at"]
