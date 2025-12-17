from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import AuditLog


def log_action(  # noqa: PLR0913
    action: str,
    *,
    actor: object | None = None,
    message: str = "",
    model_name: str = "",
    record_id: int | None = None,
    before: dict | list | None = None,
    after: dict | list | None = None,
    ip_address: str = "",
) -> None:
    user_model = get_user_model()
    actor_user = actor if isinstance(actor, user_model) else None
    AuditLog.objects.create(
        action=action,
        actor=actor_user,
        message=message,
        model_name=model_name,
        record_id=record_id,
        before=before,
        after=after,
        ip_address=ip_address,
    )
