from django.contrib import admin

from hr_payroll.notifications import models


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "recipient", "title", "message", "notification_type"]
    search_fields = ["title", "message", "notification_type", "related_link"]
    list_filter = ["notification_type", "is_read", "created_at"]
