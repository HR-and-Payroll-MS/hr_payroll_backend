from django.contrib.auth import password_validation
from django.core.exceptions import ObjectDoesNotExist
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
    employee_id = serializers.SerializerMethodField()

    # Make username & email explicitly read-only to preserve auto-generation invariant
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "employee_id",
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

    def get_employee_id(self, obj: User) -> int | None:
        # `Employee` is an optional one-to-one reverse relation
        # (related_name='employee').
        # Avoid raising if the user has no employee profile yet.
        try:
            employee = obj.employee
        except (AttributeError, ObjectDoesNotExist):  # pragma: no cover
            return None
        return getattr(employee, "pk", None)

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


class PasswordUpdateSerializer(serializers.Serializer):
    """Serializer to update the current user's password.

    Accepts either `old_password` or `current_password` plus `new_password`.
    Optionally validates `confirm_password` when provided.
    """

    old_password = serializers.CharField(write_only=True, required=False)
    current_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Permission layer guards this, but keep a defensive check.
        if user is None or not user.is_authenticated:
            raise serializers.ValidationError({"detail": "Authentication required"})

        old_pw = attrs.get("old_password") or attrs.get("current_password")
        if not old_pw:
            raise serializers.ValidationError(
                {"current_password": "This field is required."}
            )

        if not user.check_password(old_pw):
            raise serializers.ValidationError(
                {"current_password": "Incorrect password."}
            )

        new_pw = attrs.get("new_password")
        confirm = attrs.get("confirm_password")
        if confirm is not None and confirm != new_pw:
            raise serializers.ValidationError(
                {"confirm_password": "Does not match new_password."}
            )

        password_validation.validate_password(new_pw, user=user)
        attrs["user"] = user
        attrs["validated_new_password"] = new_pw
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        new_pw = self.validated_data["validated_new_password"]
        user.set_password(new_pw)
        if hasattr(user, "updated_at"):
            user.save(update_fields=["password", "updated_at"])
        else:
            user.save()
        return user
