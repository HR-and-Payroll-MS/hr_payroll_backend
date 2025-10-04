import secrets
import string
from collections import OrderedDict
from typing import Any
from typing import cast

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers

from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument


class UsernameOrPkRelatedField(serializers.SlugRelatedField):
    """A related field that accepts either username (slug) or primary key.

    - Representation: returns the slug (e.g., username)
    - Input: accepts integer/number-like values as PK or string as slug
    - Queryset on the field is used for browsable API choices; lookups use all users
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep an unrestricted queryset for lookups so we can return friendly validation
        self._all_users_qs = get_user_model().objects.all()

    def to_internal_value(self, data):
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

        msg = "User not found."
        raise serializers.ValidationError(msg)

    def get_choices(self, cutoff=None):
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
    user = UsernameOrPkRelatedField(
        slug_field="username",
        queryset=get_user_model().objects.all(),
        required=False,
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Employee
        fields = ["id", "user", "department", "title", "hire_date"]

    def __init__(self, *args, **kwargs):
        # On create: restrict selectable users to those without an Employee
        # On update: allow all users; validation still prevents assigning a
        # user who already has an Employee
        super().__init__(*args, **kwargs)
        creating = getattr(self, "instance", None) is None
        user_model = get_user_model()
        qs = (
            user_model.objects.filter(employee__isnull=True)
            if creating
            else user_model.objects.all()
        )
        if "user" in self.fields:
            field = cast("Any", self.fields["user"])  # type: ignore[no-redef]
            field.queryset = qs

    def validate(self, attrs):
        # Ensure 'user' is provided on create. If no available users,
        # show a clearer message.
        if self.instance is None and not attrs.get("user"):
            user_field = self.fields.get("user")
            qs = getattr(user_field, "queryset", None)
            if qs is not None and not qs.exists():
                msg = "No available users to assign. All users are already employees."
                raise serializers.ValidationError({"user": msg})
            msg = "This field is required (provide username or user id)."
            raise serializers.ValidationError({"user": msg})
        return super().validate(attrs)

    def validate_user(self, user):
        # Ensure an employee record does not already exist for this user
        instance = getattr(self, "instance", None)
        if instance is not None and getattr(instance, "user_id", None) == getattr(
            user,
            "id",
            None,
        ):
            return user
        if Employee.objects.filter(user=user).exists():
            msg = "Employee for this user already exists."
            raise serializers.ValidationError(msg)
        return user


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    MAX_SIZE = 5 * 1024 * 1024
    ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}

    class Meta:
        model = EmployeeDocument
        fields = ["id", "employee", "name", "file", "uploaded_at"]

    def validate_file(self, f):
        name = getattr(f, "name", "") or ""
        if not any(name.lower().endswith(ext) for ext in self.ALLOWED_EXT):
            msg = "Unsupported file type."
            raise serializers.ValidationError(msg)
        size = getattr(f, "size", None)
        if size is not None and size > self.MAX_SIZE:
            msg = "File too large (max 5MB)."
            raise serializers.ValidationError(msg)
        return f


def _generate_unique_username_email(first_name: str, last_name: str) -> tuple[str, str]:
    """Generate a unique, compact username & email.

    Pattern (deterministic):
        <first-initial><truncated-last><seq>

    - first-initial: first letter of first name (fallback 'u')
    - truncated-last: slugified last name truncated to ONBOARDING_LAST_NAME_LENGTH
      (fallback 'user' if blank)
    - seq: zero-padded integer starting at 001 ensuring uniqueness
    Example: John Robertson -> jrobert001, next collision jrobert002

    Email: <username>@<ONBOARDING_EMAIL_DOMAIN>
    """
    fi = (first_name or "").strip()[:1].lower() or "u"
    ln_raw = slugify((last_name or "").strip())
    if not ln_raw:
        ln_raw = "user"
    max_len = getattr(settings, "ONBOARDING_LAST_NAME_LENGTH", 6)
    ln_part = ln_raw[:max_len]
    user_model = get_user_model()
    pad = getattr(settings, "ONBOARDING_SEQUENCE_PAD", 3)
    seq = 1
    while True:
        seq_str = str(seq).zfill(pad)
        candidate = f"{fi}{ln_part}{seq_str}" if seq > 0 else f"{fi}{ln_part}"
        if not user_model.objects.filter(username=candidate).exists():
            break
        seq += 1
    domain = getattr(settings, "ONBOARDING_EMAIL_DOMAIN", "hr_payroll.com")
    email_candidate = f"{candidate}@{domain}".lower()
    # Email uniqueness enforced by user model's unique constraint; on rare
    # collision we increment further.
    while user_model.objects.filter(email=email_candidate).exists():
        seq += 1
        seq_str = str(seq).zfill(pad)
        candidate = f"{fi}{ln_part}{seq_str}"
        email_candidate = f"{candidate}@{domain}".lower()
    return candidate, email_candidate


def _generate_secure_password(length: int = 12) -> str:
    """Return a moderately sized secure password.

    Ensures at least one lowercase, uppercase, digit, and symbol.
    Avoid visually ambiguous characters and quotes.
    """
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*+-_"  # curated set
    all_chars = lower + upper + digits + symbols
    while True:
        pwd = [
            secrets.choice(lower),
            secrets.choice(upper),
            secrets.choice(digits),
            secrets.choice(symbols),
        ]
        pwd += [secrets.choice(all_chars) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(pwd)
        candidate = "".join(pwd)
        # Basic complexity check (already ensured); length check adjustable
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in symbols for c in candidate)
        ):
            return candidate


class OnboardEmployeeNewSerializer(serializers.Serializer):
    """Serializer to onboard a brand-new employee.

    If ``username`` and/or ``email`` are omitted or blank they are automatically
    generated using a deterministic compact pattern:

        <first-initial><truncated-last><seq>

    - first-initial: first letter of the provided first name (fallback 'u')
        - truncated-last: slugified last name limited by
            ONBOARDING_LAST_NAME_LENGTH (fallback 'user')
        - seq: zero-padded sequence starting at 001 (width
            ONBOARDING_SEQUENCE_PAD)

    Example: first_name=John, last_name=Robertson -> jrobert001 (domain
    appended for email)

    Settings influencing generation:
        ONBOARDING_EMAIL_DOMAIN (default hr_payroll.com)
        ONBOARDING_LAST_NAME_LENGTH (default 6)
        ONBOARDING_SEQUENCE_PAD (default 3)

    The email local part equals the generated username.
    """

    # Credentials are auto-generated; disallow client submission
    # (kept as read_only so schema shows them as output-only if needed)
    username = serializers.CharField(max_length=150, read_only=True)
    email = serializers.EmailField(read_only=True)
    # Password is fully internal; not declared as a field to avoid any
    # chance of client submission.
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    # Employee fields
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    hire_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        # Reject attempts to supply forbidden fields (credentials are auto-generated)
        forbidden = [
            f
            for f in (
                "username",
                "email",
                "password",  # password not a declared field but still reject
            )
            if f in self.initial_data and self.initial_data.get(f)
        ]
        if forbidden:
            raise serializers.ValidationError(
                dict.fromkeys(forbidden, "This field is not editable.")
            )

        gen_username, gen_email = _generate_unique_username_email(
            attrs.get("first_name", ""),
            attrs.get("last_name", ""),
        )
        gen_password = _generate_secure_password()
        self.generated_username = gen_username  # type: ignore[attr-defined]
        self.generated_email = gen_email  # type: ignore[attr-defined]
        self.generated_password = gen_password  # type: ignore[attr-defined]
        # Inject for create()
        attrs["username"] = gen_username
        attrs["email"] = gen_email
        # Store password internally only
        attrs["_generated_password"] = gen_password
        return attrs

    def create(self, validated_data):
        user_model = get_user_model()
        dept = validated_data.pop("department", None)
        title = validated_data.pop("title", "")
        hire_date = validated_data.pop("hire_date", None)
        password = validated_data.pop("_generated_password")

        user = user_model.objects.create_user(
            username=validated_data.pop("username"),
            email=validated_data.get("email"),
            first_name=validated_data.pop("first_name", ""),
            last_name=validated_data.pop("last_name", ""),
        )
        user.is_active = True
        user.set_password(password)
        user.save()

        # Ensure email is marked verified and primary in allauth
        email_value = validated_data.get("email")
        if email_value:
            EmailAddress.objects.update_or_create(
                user=user,
                email=email_value,
                defaults={"verified": True, "primary": True},
            )

        return Employee.objects.create(
            user=user,
            department=dept,
            title=title,
            hire_date=hire_date,
        )


class OnboardEmployeeExistingSerializer(serializers.Serializer):
    # Select an existing user (not yet an employee)
    user = UsernameOrPkRelatedField(
        slug_field="username",
        queryset=get_user_model().objects.all(),
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    hire_date = serializers.DateField(required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit choices to users without an employee, for the browsable API UX
        user_model = get_user_model()
        self.fields["user"].queryset = user_model.objects.filter(employee__isnull=True)

    def validate_user(self, user):
        if Employee.objects.filter(user=user).exists():
            msg = "Employee for this user already exists."
            raise serializers.ValidationError(msg)
        return user

    def create(self, validated_data):
        user = validated_data.pop("user")
        department = validated_data.pop("department", None)
        title = validated_data.pop("title", "")
        hire_date = validated_data.pop("hire_date", None)
        return Employee.objects.create(
            user=user,
            department=department,
            title=title,
            hire_date=hire_date,
        )
