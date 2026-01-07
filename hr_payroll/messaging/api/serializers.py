from django.contrib.auth import get_user_model
from rest_framework import serializers

from hr_payroll.messaging.models import Chat
from hr_payroll.messaging.models import Message

User = get_user_model()


class ChatSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    participant_ids = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = [
            "id",
            "title",
            "participant_ids",
            "participant_names",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_id(self, obj: Chat) -> str:
        return str(obj.pk)

    def get_participant_ids(self, obj: Chat):
        return list(obj.participants.values_list("id", flat=True))

    def get_participant_names(self, obj: Chat):
        return [(u.get_full_name() or u.username) for u in obj.participants.all()]

    def get_created_by_name(self, obj: Chat) -> str:
        user = getattr(obj, "created_by", None)
        if not user:
            return ""
        return user.get_full_name() or user.username


class ChatCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=True
    )

    def validate_participant_ids(self, value):
        ids = [int(v) for v in value or []]
        users = User.objects.filter(id__in=ids)
        found = set(users.values_list("id", flat=True))
        missing = [v for v in ids if v not in found]
        if missing:
            msg = f"Unknown users: {missing}"
            raise serializers.ValidationError(msg)
        return list(found)

    def create(self, validated):
        request = (
            self.context.get("request") if isinstance(self.context, dict) else None
        )
        creator = getattr(request, "user", None)
        chat = Chat.objects.create(title=validated["title"], created_by=creator)
        chat.participants.set(
            validated["participant_ids"] + ([creator.id] if creator else [])
        )
        return chat


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    chat_id = serializers.IntegerField(source="chat.id", read_only=True)
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "chat_id", "sender", "sender_name", "content", "created_at"]
        read_only_fields = ["id", "sender", "created_at", "chat_id"]

    def get_id(self, obj: Message) -> str:
        return str(obj.pk)

    def get_sender_name(self, obj: Message) -> str:
        u = getattr(obj, "sender", None)
        if not u:
            return ""
        return u.get_full_name() or u.username


class MessageCreateSerializer(serializers.Serializer):
    chat_id = serializers.IntegerField(min_value=1)
    content = serializers.CharField()

    def validate_chat_id(self, value):
        try:
            Chat.objects.get(pk=value)
        except Chat.DoesNotExist:
            msg = "Chat not found"
            raise serializers.ValidationError(msg) from None
        return value

    def create(self, validated):
        request = (
            self.context.get("request") if isinstance(self.context, dict) else None
        )
        sender = getattr(request, "user", None)
        chat = Chat.objects.get(pk=validated["chat_id"])  # validated above
        return Message.objects.create(
            chat=chat, sender=sender, content=validated["content"]
        )
