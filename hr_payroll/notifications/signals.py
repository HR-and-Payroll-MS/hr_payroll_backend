import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .socketio import emit_notification_to_user

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def send_notification_ws(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = f"user_{instance.recipient.id}"
        logger.warning("DEBUG: Sending WS notification to group: %s", group_name)
        payload = {
            "title": instance.title,
            "message": instance.message,
            "type": instance.notification_type,
            "link": instance.related_link,
            "id": instance.id,
        }

        # Raw Channels consumer
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "send_notification",
                "message": payload,
            },
        )

        # Socket.IO (React frontend)
        emit_notification_to_user(instance.recipient_id, payload)
