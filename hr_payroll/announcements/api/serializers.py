from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers

from hr_payroll.announcements.models import Announcement
from hr_payroll.announcements.models import AnnouncementRead

User = get_user_model()


class AnnouncementSerializer(serializers.ModelSerializer):
    audience_groups = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    read = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "message",
            "audience_groups",
            "created_at",
            "created_by_name",
            "read",
            "read_at",
        ]
        read_only_fields = fields

    def _read_record(self, obj: Announcement):
        request = (
            self.context.get("request") if isinstance(self.context, dict) else None
        )
        user = getattr(request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return None
        return AnnouncementRead.objects.filter(announcement=obj, user=user).first()

    def get_audience_groups(self, obj: Announcement):
        return list(obj.audience_groups.values_list("name", flat=True))

    def get_created_by_name(self, obj: Announcement) -> str:
        creator = getattr(obj, "created_by", None)
        if not creator:
            return ""
        return getattr(creator, "get_full_name", lambda: "")() or getattr(
            creator, "username", ""
        )

    def get_read(self, obj: Announcement) -> bool:
        read_record = self._read_record(obj)
        return bool(read_record)

    def get_read_at(self, obj: Announcement):
        read_record = self._read_record(obj)
        return getattr(read_record, "read_at", None)


class AnnouncementCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    audience_group_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )

    def validate_audience_group_ids(self, value):
        if not value:
            return []
        groups = Group.objects.filter(id__in=value)
        found_ids = set(groups.values_list("id", flat=True))
        missing = [gid for gid in value if gid not in found_ids]
        if missing:
            msg = f"Unknown groups: {missing}"
            raise serializers.ValidationError(msg)
        return list(found_ids)

    def create(self, validated_data):
        request = (
            self.context.get("request") if isinstance(self.context, dict) else None
        )
        user = getattr(request, "user", None)
        audience_ids = validated_data.get("audience_group_ids") or []
        announcement = Announcement.objects.create(
            title=validated_data["title"],
            message=validated_data["message"],
            created_by=user
            if user and getattr(user, "is_authenticated", False)
            else None,
        )
        if audience_ids:
            announcement.audience_groups.set(audience_ids)
        return announcement
