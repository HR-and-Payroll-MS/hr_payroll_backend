from django.urls import reverse
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

    url = serializers.SerializerMethodField()

    def get_url(self, obj: User) -> str:
        request = self.context.get("request")
        if request is None:
            # Fallback to default api namespace
            return reverse("api:user-detail", kwargs={"username": obj.username})
        namespace = getattr(
            getattr(request, "resolver_match", None),
            "namespace",
            "api",
        )
        # Choose view name based on namespace
        view_name = "api_v1:user-detail" if namespace == "api_v1" else "api:user-detail"
        return request.build_absolute_uri(
            reverse(view_name, kwargs={"username": obj.username}),
        )

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_manager_or_admin = False
        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_staff", False):
                is_manager_or_admin = True
            else:
                groups = getattr(user, "groups", None)
                is_manager_or_admin = bool(
                    groups and groups.filter(name__in=["Admin", "Manager"]).exists(),
                )

        # Everyone can change their first/last name
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)

        # Only Admin/Manager can change email/username via this endpoint
        if is_manager_or_admin:
            instance.email = validated_data.get("email", instance.email)
            instance.username = validated_data.get("username", instance.username)

        instance.save()
        return instance
