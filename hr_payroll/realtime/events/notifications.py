from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:  # import for type checking only
    from hr_payroll.notifications.models import Notification
from hr_payroll.realtime.socketio import emit_event_to_user


def build_notification_payload(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "type": notification.notification_type,
        "link": notification.related_link,
    }


def publish_notification_created(notification: Notification) -> None:
    """Publish a newly created Notification to the recipient in realtime."""

    payload = build_notification_payload(notification)

    # Socket.IO (React frontend)
    emit_event_to_user(notification.recipient_id, "notification", payload)
