from django.contrib import admin

from hr_payroll.audit import models


@admin.register(models.AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["id", "action", "actor", "message", "model_name"]
    search_fields = ["action", "message", "model_name", "ip_address"]
    list_filter = ["created_at"]
