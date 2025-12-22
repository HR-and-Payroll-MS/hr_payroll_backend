from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from hr_payroll.notifications.models import Notification

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    """Read serializer for notifications."""

    unread = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient",
            "title",
            "message",
            "notification_type",
            "is_read",
            "unread",
            "created_at",
            "related_link",
        )
        read_only_fields = (
            "id",
            "recipient",
            "is_read",
            "created_at",
        )

    def get_unread(self, obj: Notification) -> bool:
        return not bool(obj.is_read)


class NotificationCreateSerializer(serializers.Serializer):
    """Create serializer.

    Supports creating one Notification per recipient.

    Accepted targeting forms (exactly one is required):
    - recipient_id: int
    - receiver_group: str (Django Group name)
    - receivers: list[ int | str ]
      - int: user id
      - str: "ALL" (broadcast to all users) or a Group name
    """

    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    notification_type = serializers.ChoiceField(
        choices=Notification.Type.choices,
        required=False,
        default=Notification.Type.OTHER,
    )
    related_link = serializers.CharField(required=False, allow_blank=True, default="")

    # Accept either int or numeric string, and tolerate "" (treated as missing).
    recipient_id = serializers.CharField(required=False, allow_blank=True)
    receiver_group = serializers.CharField(required=False, allow_blank=True)
    receivers = serializers.ListField(child=serializers.JSONField(), required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Normalize empty values so frontend forms can submit repeatedly without
        # accidentally sending multiple targets (e.g. receiver_group="" plus receivers).
        recipient_id = attrs.get("recipient_id")
        if isinstance(recipient_id, str):
            recipient_id = recipient_id.strip()
            if not recipient_id:
                attrs.pop("recipient_id", None)
            elif recipient_id.isdigit():
                attrs["recipient_id"] = int(recipient_id)
            else:
                msg = "Must be an integer."
                raise serializers.ValidationError({"recipient_id": msg})

        receiver_group = attrs.get("receiver_group")
        if isinstance(receiver_group, str) and not receiver_group.strip():
            attrs.pop("receiver_group", None)

        receivers = attrs.get("receivers")
        if isinstance(receivers, list) and len(receivers) == 0:
            attrs.pop("receivers", None)

        targets = [
            "recipient_id" in attrs,
            "receiver_group" in attrs,
            "receivers" in attrs,
        ]
        if sum(targets) != 1:
            msg = "Provide exactly one of recipient_id, receiver_group, receivers."
            raise serializers.ValidationError(msg)
        return attrs
