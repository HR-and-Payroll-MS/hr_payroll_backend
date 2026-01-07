from typing import Any

from rest_framework import mixins
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.messaging.api.serializers import ChatCreateSerializer
from hr_payroll.messaging.api.serializers import ChatSerializer
from hr_payroll.messaging.api.serializers import MessageCreateSerializer
from hr_payroll.messaging.api.serializers import MessageSerializer
from hr_payroll.messaging.models import Chat
from hr_payroll.messaging.models import Message
from hr_payroll.realtime.socketio import emit_event_to_user


class ChatViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatSerializer
    queryset = Chat.objects.all().prefetch_related("participants")

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return Chat.objects.none()
        return self.queryset.filter(participants=user)

    def create(self, request, *args, **kwargs):
        ser = ChatCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        chat = ser.save()
        out = ChatSerializer(chat, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)


class MessageViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    queryset = Message.objects.select_related("sender", "chat", "chat__created_by")

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return Message.objects.none()
        chat_id = self.request.query_params.get("chat_id")
        qs = self.queryset.filter(chat__participants=user)
        if chat_id and str(chat_id).isdigit():
            qs = qs.filter(chat_id=int(chat_id))
        return qs

    def create(self, request, *args, **kwargs):
        ser = MessageCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        msg = ser.save()
        out = MessageSerializer(msg, context={"request": request}).data
        # Emit socket event to all chat participants
        participants = list(msg.chat.participants.values_list("id", flat=True))
        payload: dict[str, Any] = {
            "id": out["id"],
            "chat_id": msg.chat_id,
            "sender_id": msg.sender_id,
            "sender_name": out["sender_name"],
            "content": msg.content,
            "created_at": out["created_at"],
        }
        for uid in participants:
            emit_event_to_user(uid, "chat.message", payload)
        return Response(out, status=status.HTTP_201_CREATED)
