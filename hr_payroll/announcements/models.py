from django.conf import settings
from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Category from announcementPolicy (e.g., Urgent, General)",
    )
    audience_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="announcements",
        help_text="If empty, announcement is visible to all users.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="reads"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_reads",
    )
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("announcement", "user")
        ordering = ["-read_at"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"Read<{self.announcement_id}:{self.user_id}>"
