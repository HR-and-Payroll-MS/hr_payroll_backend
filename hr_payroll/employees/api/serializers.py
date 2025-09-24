from django.contrib.auth import get_user_model
from collections import OrderedDict
from typing import cast
from rest_framework.relations import RelatedField
from rest_framework import serializers

from ..models import Department, Employee, EmployeeDocument


class UsernameOrPkRelatedField(serializers.SlugRelatedField):
    """A related field that accepts either username (slug) or primary key.

    - Representation: returns the slug (e.g., username)
    - Input: accepts integer/number-like values as PK or string as slug
    - Queryset on the field is used for browsable API choices; lookups use all users
    """

    def __init__(self, *args, **kwargs):  # noqa: D401
        super().__init__(*args, **kwargs)
        # Keep an unrestricted queryset for lookups so we can return friendly validation
        self._all_users_qs = get_user_model().objects.all()

    def to_internal_value(self, data):  # noqa: D401, ANN001
        # Try by PK if numeric
        try:
            pk = int(data)  # handles int and numeric strings
        except (TypeError, ValueError):
            pk = None

        if pk is not None:
            try:
                return self._all_users_qs.get(pk=pk)
            except get_user_model().DoesNotExist:  # fall through to slug lookup
                pass

        # Fallback to slug (username)
        if isinstance(data, str):
            try:
                slug_attr = self.slug_field or "username"
                return self._all_users_qs.get(**{slug_attr: data})
            except get_user_model().DoesNotExist:
                pass

        raise serializers.ValidationError("User not found.")

    def get_choices(self, cutoff=None):  # noqa: D401, ANN001
        """Show username and id side-by-side in the browsable API dropdown."""
        qs = self.get_queryset()
        if qs is None:
            return OrderedDict()
        choices = OrderedDict()
        slug_attr = self.slug_field or "username"
        for item in qs:
            key = self.to_representation(item)
            username = getattr(item, slug_attr)
            pk_val = getattr(item, "pk", "")
            choices[key] = f"{username} (id: {pk_val})"
        return choices


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description"]


class EmployeeSerializer(serializers.ModelSerializer):
    # Single prompt: accept username or id; represent as username on read
    user = UsernameOrPkRelatedField(slug_field="username", queryset=get_user_model().objects.all(), required=False)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Employee
        fields = ["id", "user", "department", "title", "hire_date"]

    def __init__(self, *args, **kwargs):  # noqa: D401
        # Dynamically restrict selectable users when creating: only users without an Employee
        # On update, allow all users; validation will still prevent assigning a user who already has an Employee
        super().__init__(*args, **kwargs)
        creating = getattr(self, "instance", None) is None
        User = get_user_model()
        qs = User.objects.filter(employee__isnull=True) if creating else User.objects.all()
        if "user" in self.fields:
            field = cast(RelatedField, self.fields["user"])  # type: ignore[no-redef]
            field.queryset = qs

    def validate(self, attrs):  # noqa: D401
        # Ensure 'user' is provided on create. If no available users, show a clearer message.
        if self.instance is None and not attrs.get("user"):
            user_field = self.fields.get("user")
            qs = getattr(user_field, "queryset", None)
            if qs is not None and not qs.exists():
                raise serializers.ValidationError({
                    "user": "No available users to assign. All users are already employees."
                })
            raise serializers.ValidationError({
                "user": "This field is required (provide username or user id)."
            })
        return super().validate(attrs)

    def validate_user(self, user):  # noqa: D401, ANN001
        # Ensure an employee record does not already exist for this user
        instance = getattr(self, "instance", None)
        if instance is not None and getattr(instance, "user_id", None) == getattr(user, "id", None):
            return user
        if Employee.objects.filter(user=user).exists():
            raise serializers.ValidationError("Employee for this user already exists.")
        return user


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    MAX_SIZE = 5 * 1024 * 1024
    ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}

    class Meta:
        model = EmployeeDocument
        fields = ["id", "employee", "name", "file", "uploaded_at"]

    def validate_file(self, f):  # noqa: D401, ANN001
        name = getattr(f, "name", "") or ""
        if not any(name.lower().endswith(ext) for ext in self.ALLOWED_EXT):
            raise serializers.ValidationError("Unsupported file type.")
        size = getattr(f, "size", None)
        if size is not None and size > self.MAX_SIZE:
            raise serializers.ValidationError("File too large (max 5MB).")
        return f
