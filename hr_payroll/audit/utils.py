from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import AuditLog


def log_action(
    action: str,
    *,
    actor: object | None = None,
    message: str = "",
) -> None:
    user_model = get_user_model()
    actor_user = actor if isinstance(actor, user_model) else None
    AuditLog.objects.create(action=action, actor=actor_user, message=message)
