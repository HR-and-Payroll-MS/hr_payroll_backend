from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from hr_payroll.audit.models import AuditLog

User = get_user_model()


class AuditActorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name"]

    def get_full_name(self, obj):
        fn = getattr(obj, "get_full_name", None)
        if callable(fn):
            return (fn() or "").strip() or None
        return None


class AuditLogSerializer(serializers.ModelSerializer):
    actor = AuditActorSerializer(allow_null=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "message",
            "model_name",
            "record_id",
            "ip_address",
            "created_at",
            "actor",
        ]
