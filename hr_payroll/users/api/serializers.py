from rest_framework import serializers

from hr_payroll.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    full_name = serializers.CharField(source="name", read_only=True)
    groups = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="name",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "groups",
            "url",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"},
        }

    def update(self, instance, validated_data):
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.email = validated_data.get("email", instance.email)

        instance.save()
        return instance
