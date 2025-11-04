from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    action = models.CharField(max_length=100)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    message = models.TextField(blank=True)
    model_name = models.CharField(max_length=150, blank=True)
    record_id = models.BigIntegerField(null=True, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        who = self.actor_id or "system"
        return f"[{self.created_at}] {who}: {self.action}"
