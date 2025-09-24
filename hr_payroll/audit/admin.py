from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor")
    list_filter = ("action", "created_at")
    search_fields = ("action", "message", "actor__username", "actor__email")
