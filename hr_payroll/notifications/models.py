from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    class Type(models.TextChoices):
        LEAVE_REQUEST = "leave_request", _("Leave Request")
        APPROVAL = "approval", _("Approval")
        REJECTION = "rejection", _("Rejection")
        BROADCAST = "broadcast", _("Broadcast")
        OTHER = "other", _("Other")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50, choices=Type.choices, default=Type.OTHER
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    related_link = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.recipient}"
