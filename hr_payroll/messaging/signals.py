from django.db.models.signals import post_save
from django.dispatch import receiver

from hr_payroll.messaging.api.serializers import MessageSerializer
from hr_payroll.messaging.models import Message
from hr_payroll.realtime.events import EVENT_CHAT_MESSAGE
from hr_payroll.realtime.socketio import emit_event_to_user


@receiver(post_save, sender=Message)
def broadcast_chat_message(sender, instance: Message, created: bool, **kwargs):  # noqa: FBT001
    """Notify chat participants of a new message."""
    if not created:
        return

    # Broadcast to all participants EXCEPT the sender
    # Ideally, we would emit to a "chat_{id}" room, but we haven't implemented
    # client-side room joining for chats yet.
    # So we iterate participants and emit to their user-specific rooms.

    # We serialize the message to send the full payload
    # Note: Using serializer inside signal can be heavy, but fine for now.
    payload = MessageSerializer(instance).data

    chat_participants = instance.chat.participants.exclude(id=instance.sender.id)

    for participant in chat_participants:
        emit_event_to_user(participant.id, EVENT_CHAT_MESSAGE, payload)
