from django.urls import NoReverseMatch
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
    id = serializers.IntegerField(read_only=True)

    # Make username & email explicitly read-only to preserve auto-generation invariant
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
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
            # Try common namespaced and non-namespaced route names
            for candidate in (
                "api_v1:user-detail",
                "api:user-detail",
                "user-detail",
            ):
                try:
                    return reverse(candidate, kwargs={"username": obj.username})
                except NoReverseMatch:
                    continue
            # Give up gracefully
            return ""

        namespace = getattr(
            getattr(request, "resolver_match", None),
            "namespace",
            None,
        )

        # Build a list of candidate view names to try in order of likelihood.
        candidates = []
        if namespace:
            candidates.append(f"{namespace}:user-detail")
        candidates.extend(
            [
                "api_v1:user-detail",
                "api:user-detail",
                "user-detail",
            ]
        )

        for view_name in candidates:
            try:
                url = reverse(view_name, kwargs={"username": obj.username})
            except NoReverseMatch:
                continue
            return request.build_absolute_uri(url)

        # If we couldn't resolve any name, return an empty string rather than raising
        # to avoid crashing serialization in environments with different router
        # registrations.
        return ""

    def update(self, instance, validated_data):
        # Enforce invariant: username & email are system-managed (onboarding rules)
        forbidden = {k for k in ("username", "email") if k in self.initial_data}
        if forbidden:
            # If client attempted to send them, raise a validation error.
            errors = {}
            for f in forbidden:
                errors[f] = (
                    "This field is read-only and auto-generated. "
                    "Use onboarding to change it."
                )
            raise serializers.ValidationError(errors)
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.save()
        return instance
