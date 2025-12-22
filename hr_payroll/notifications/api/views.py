from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.employees.api.permissions import IsAdminOrManagerCanWrite
from hr_payroll.notifications.models import Notification

from .serializers import NotificationCreateSerializer
from .serializers import NotificationSerializer

if TYPE_CHECKING:  # import for type checking only
    from collections.abc import Iterable

User = get_user_model()


def _coerce_receivers_to_user_ids(receivers: Iterable[Any]) -> set[int]:
    user_ids: set[int] = set()
    for r in receivers:
        if isinstance(r, bool) or r is None:
            continue
        if isinstance(r, int):
            user_ids.add(int(r))
            continue
        if isinstance(r, str) and r.strip().isdigit():
            user_ids.add(int(r.strip()))
            continue
    return user_ids


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """Notifications for the authenticated user.

    - list: shows request.user's notifications
    - create: creates notifications for target recipients (restricted)
    - destroy: deletes a notification (recipient only)
    - mark_read / mark_all_read
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsAdminOrManagerCanWrite()]
        return [p() for p in self.permission_classes]

    def create(self, request, *args, **kwargs):
        serializer = NotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        title: str = data["title"]
        message: str = data["message"]
        notification_type: str = data["notification_type"]
        related_link: str = data.get("related_link", "")

        recipient_ids: set[int] = set()
        if "recipient_id" in data:
            recipient_ids.add(int(data["recipient_id"]))
        elif "receiver_group" in data:
            group = Group.objects.filter(name=data["receiver_group"]).first()
            if not group:
                return Response(
                    {"detail": "Unknown receiver_group."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            recipient_ids.update(group.user_set.values_list("id", flat=True))
        else:
            receivers = data.get("receivers") or []
            # If receivers includes ALL, broadcast to all active users.
            has_all = any(
                isinstance(r, str) and r.strip().upper() == "ALL" for r in receivers
            )
            if has_all:
                recipient_ids.update(User.objects.values_list("id", flat=True))
            # Any non-ALL string is treated as a group name.
            group_names = [
                r.strip()
                for r in receivers
                if isinstance(r, str) and r.strip() and r.strip().upper() != "ALL"
            ]
            if group_names:
                recipient_ids.update(
                    User.objects.filter(groups__name__in=group_names).values_list(
                        "id", flat=True
                    )
                )
            recipient_ids.update(_coerce_receivers_to_user_ids(receivers))

        if not recipient_ids:
            return Response(
                {"detail": "No recipients resolved from payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            created: list[Notification] = [
                Notification.objects.create(
                    recipient_id=rid,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    related_link=related_link,
                )
                for rid in sorted(recipient_ids)
            ]

        # Return created notifications (single object for single-recipient payload).
        if len(created) == 1:
            out = NotificationSerializer(created[0], context={"request": request}).data
            return Response(out, status=status.HTTP_201_CREATED)
        out_many = NotificationSerializer(
            created, many=True, context={"request": request}
        ).data
        return Response(out_many, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
