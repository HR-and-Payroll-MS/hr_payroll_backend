from django import forms
from django.contrib import admin

from hr_payroll.efficiency.models import EfficiencyEvaluation
from hr_payroll.efficiency.models import EfficiencyTemplate


@admin.register(EfficiencyTemplate)
class EfficiencyTemplateAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "department", "is_active", "version", "updated_at"]
    list_filter = ["is_active", "department"]
    search_fields = ["title", "department__name"]
    readonly_fields = ["created_at", "updated_at"]
    formfield_overrides = {
        forms.JSONField: {
            "widget": forms.Textarea(
                attrs={
                    "rows": 12,
                    "cols": 120,
                }
            )
        }
    }


@admin.register(EfficiencyEvaluation)
class EfficiencyEvaluationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "employee",
        "department",
        "template",
        "status",
        "total_efficiency",
        "created_at",
    ]
    list_filter = ["status", "department", "template"]
    search_fields = [
        "employee__user__username",
        "employee__user__email",
        "template__title",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "total_achieved",
        "total_possible",
        "total_efficiency",
    ]
    formfield_overrides = {
        forms.JSONField: {
            "widget": forms.Textarea(
                attrs={
                    "rows": 12,
                    "cols": 120,
                }
            )
        }
    }
