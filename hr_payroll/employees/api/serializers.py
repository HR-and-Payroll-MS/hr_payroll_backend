import logging
import os
import secrets
import string
from collections import OrderedDict
from contextlib import suppress
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
from hr_payroll.employees.models import Position
from hr_payroll.employees.services.cv_parser import parse_cv

logger = logging.getLogger(__name__)


class NullablePKRelatedField(serializers.PrimaryKeyRelatedField):
    """PK field that treats blank strings as None when allow_null=True.

    This improves browsable API UX where empty selects submit "" instead of null.
    """

    def to_internal_value(self, data):  # type: ignore[override]
        if self.allow_null and (data is None or data == ""):
            return None
        return super().to_internal_value(data)


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
    manager = NullablePKRelatedField(
        queryset=Employee.objects.filter(user__groups__name="Manager"),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "description",
            "location",
            "budget_code",
            "manager",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        # Include commonly useful identity fields only
        fields = ["id", "username", "email", "first_name", "last_name", "is_active"]


class PositionSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "title",
            "department",
            "salary_grade",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class EmployeeSerializer(serializers.ModelSerializer):
    # Input: still allow setting by username or id. Output: nested user + department.
    user = UsernameOrPkRelatedField(
        slug_field="username",
        queryset=get_user_model().objects.all(),
        required=False,
        write_only=True,
    )
    department = NullablePKRelatedField(
        queryset=Department.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    supervisor = NullablePKRelatedField(
        queryset=Employee.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    position = NullablePKRelatedField(
        queryset=Position.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Employee
        fields = [
            "id",
            "user",
            "department",
            "title",
            "hire_date",
            "supervisor",
            "position",
            "national_id",
            "gender",
            "date_of_birth",
            "employment_status",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):  # type: ignore[override]
        base = super().to_representation(instance)
        # Replace user pk/slug with nested structure
        user_obj = getattr(instance, "user", None)
        if user_obj is not None:
            base["user"] = UserNestedSerializer(user_obj).data
        # Replace department id with nested department if present
        dept = getattr(instance, "department", None)
        if dept is not None:
            base["department"] = DepartmentSerializer(dept).data
        else:
            base["department"] = None
        # Replace supervisor id with a minimal nested representation
        sup = getattr(instance, "supervisor", None)
        if sup is not None:
            base["supervisor"] = {
                "id": sup.id,
                "user": {
                    "id": getattr(sup.user, "id", None),
                    "username": getattr(sup.user, "username", None),
                },
            }
        else:
            base["supervisor"] = None
        # Replace position id with nested position
        pos = getattr(instance, "position", None)
        if pos is not None:
            base["position"] = PositionSerializer(pos).data
        else:
            base["position"] = None
        return base

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


class CVParseUploadSerializer(serializers.Serializer):
    """Upload-only serializer for CV parsing endpoint."""

    cv_file = serializers.FileField(required=True, allow_empty_file=False)


class CVParsedDataSerializer(serializers.Serializer):
    """Schema for parsed CV data returned to prefill forms."""

    full_name = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    date_of_birth = serializers.CharField(required=False)
    national_id = serializers.CharField(required=False)
    gender = serializers.CharField(required=False)


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
    # Convenience: accept a single full_name and split into first/last if provided
    full_name = serializers.CharField(required=False, allow_blank=True)
    # Employee fields (superset of regular Employee writable fields)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    hire_date = serializers.DateField(required=False, allow_null=True)
    supervisor = NullablePKRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True
    )
    position = NullablePKRelatedField(
        queryset=Position.objects.all(), required=False, allow_null=True
    )
    national_id = serializers.CharField(max_length=50, required=False, allow_blank=True)
    gender = serializers.ChoiceField(
        choices=Employee.Gender.choices, required=False, allow_blank=False
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    employment_status = serializers.ChoiceField(
        choices=Employee.EmploymentStatus.choices, required=False
    )
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    employee_email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    # Optional CV upload as raw bytes (when used via multipart/form-data)
    cv_file = serializers.FileField(required=False, allow_empty_file=False)

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

        # If full_name provided and first/last omitted, split it
        full_name = self.initial_data.get("full_name")
        if full_name and not attrs.get("first_name") and not attrs.get("last_name"):
            parts = str(full_name).strip().split()
            if parts:
                attrs["first_name"] = parts[0]
                attrs["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""

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
        cv_file = validated_data.pop("cv_file", None)
        # If CV provided, parse and prefill missing fields
        if cv_file is not None:
            with suppress(Exception):
                content = cv_file.read()
                extracted = parse_cv(content, getattr(cv_file, "name", None))
                with suppress(Exception):
                    cv_file.seek(0)
                # Debug log the extracted payload for local development
                cv_dbg = (
                    getattr(settings, "DEBUG", False)
                    or os.environ.get("ENABLE_CV_DEBUG") == "1"
                )
                if cv_dbg:
                    logger.info("Onboard(new): CV extracted: %s", extracted)
                # Fill only if not provided explicitly
                for src_key, dst_key in (
                    ("first_name", "first_name"),
                    ("last_name", "last_name"),
                    ("email", "employee_email"),
                    ("phone", "phone"),
                    ("date_of_birth", "date_of_birth"),
                    ("full_name", None),  # handled by split logic already
                ):
                    if (
                        dst_key
                        and not validated_data.get(dst_key)
                        and extracted.get(src_key)
                    ):
                        validated_data[dst_key] = extracted[src_key]
                    if not dst_key and extracted.get(src_key):
                        # if full_name was provided from CV and no names set
                        if not validated_data.get(
                            "first_name"
                        ) and not validated_data.get("last_name"):
                            parts = str(extracted[src_key]).split()
                            if parts:
                                validated_data["first_name"] = parts[0]
                                validated_data["last_name"] = (
                                    " ".join(parts[1:]) if len(parts) > 1 else ""
                                )
        dept = validated_data.pop("department", None)
        title = validated_data.pop("title", "")
        hire_date = validated_data.pop("hire_date", None)
        supervisor = validated_data.pop("supervisor", None)
        position = validated_data.pop("position", None)
        national_id = validated_data.pop("national_id", "")
        # Default gender to empty string to satisfy NOT NULL constraint on CharField
        gender = validated_data.pop("gender", "")
        date_of_birth = validated_data.pop("date_of_birth", None)
        employment_status = validated_data.pop(
            "employment_status", Employee.EmploymentStatus.ACTIVE
        )
        first_name_emp = validated_data.pop("first_name", "")
        last_name_emp = validated_data.pop("last_name", "")
        employee_email = validated_data.pop("employee_email", "") or None
        phone = validated_data.pop("phone", "")
        address = validated_data.pop("address", "")
        password = validated_data.pop("_generated_password")

        user = user_model.objects.create_user(
            username=validated_data.pop("username"),
            email=validated_data.get("email"),
            first_name=first_name_emp,
            last_name=last_name_emp,
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

        employee = Employee.objects.create(
            user=user,
            department=dept,
            title=title,
            hire_date=hire_date,
            supervisor=supervisor,
            position=position,
            national_id=national_id,
            gender=gender,
            date_of_birth=date_of_birth,
            employment_status=employment_status,
            first_name=first_name_emp,
            last_name=last_name_emp,
            email=employee_email,
            phone=phone,
            address=address,
            # is_active is now auto-synced from employment_status
        )
        # Persist uploaded CV as EmployeeDocument if provided
        if cv_file is not None:
            with suppress(Exception):
                EmployeeDocument.objects.create(
                    employee=employee,
                    name=getattr(cv_file, "name", "cv.pdf"),
                    file=cv_file,
                )
        return employee


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
    supervisor = NullablePKRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True
    )
    position = NullablePKRelatedField(
        queryset=Position.objects.all(), required=False, allow_null=True
    )
    national_id = serializers.CharField(max_length=50, required=False, allow_blank=True)
    gender = serializers.ChoiceField(
        choices=Employee.Gender.choices, required=False, allow_blank=False
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    employment_status = serializers.ChoiceField(
        choices=Employee.EmploymentStatus.choices, required=False
    )
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    # Convenience: accept a single full_name and split into first/last if provided
    full_name = serializers.CharField(required=False, allow_blank=True)
    employee_email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    cv_file = serializers.FileField(required=False, allow_empty_file=False)

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

    def create(self, validated_data):  # noqa: C901, PLR0912, PLR0915 - acceptable orchestration here
        user = validated_data.pop("user")
        cv_file = validated_data.pop("cv_file", None)
        department = validated_data.pop("department", None)
        title = validated_data.pop("title", "")
        hire_date = validated_data.pop("hire_date", None)
        supervisor = validated_data.pop("supervisor", None)
        position = validated_data.pop("position", None)
        national_id = validated_data.pop("national_id", "")
        # Default gender to empty string to satisfy NOT NULL constraint on CharField
        gender = validated_data.pop("gender", "")
        date_of_birth = validated_data.pop("date_of_birth", None)
        employment_status = validated_data.pop(
            "employment_status", Employee.EmploymentStatus.ACTIVE
        )
        # If full_name provided, split unless explicit first/last provided
        first_name_emp = validated_data.pop("first_name", "")
        last_name_emp = validated_data.pop("last_name", "")
        full_name = self.initial_data.get("full_name")
        if full_name and not first_name_emp and not last_name_emp:
            parts = str(full_name).strip().split()
            if parts:
                first_name_emp = parts[0]
                last_name_emp = " ".join(parts[1:]) if len(parts) > 1 else ""
        # Autofill from the selected user if still missing
        if not first_name_emp:
            first_name_emp = getattr(user, "first_name", "") or ""
        if not last_name_emp:
            last_name_emp = getattr(user, "last_name", "") or ""
        employee_email = validated_data.pop("employee_email", "") or None
        if not employee_email:
            employee_email = getattr(user, "email", None) or None
        phone = validated_data.pop("phone", "")
        address = validated_data.pop("address", "")
        # Prefill from CV if provided
        if cv_file is not None:
            with suppress(Exception):
                content = cv_file.read()
                extracted = parse_cv(content, getattr(cv_file, "name", None))
                with suppress(Exception):
                    cv_file.seek(0)
                cv_dbg = (
                    getattr(settings, "DEBUG", False)
                    or os.environ.get("ENABLE_CV_DEBUG") == "1"
                )
                if cv_dbg:
                    logger.info("Onboard(existing): CV extracted: %s", extracted)
                if not first_name_emp and extracted.get("first_name"):
                    first_name_emp = extracted["first_name"]
                if not last_name_emp and extracted.get("last_name"):
                    last_name_emp = extracted["last_name"]
                if not employee_email and extracted.get("email"):
                    employee_email = extracted["email"]
                if not phone and extracted.get("phone"):
                    phone = extracted["phone"]
                if not date_of_birth and extracted.get("date_of_birth"):
                    date_of_birth = extracted["date_of_birth"]

        employee = Employee.objects.create(
            user=user,
            department=department,
            title=title,
            hire_date=hire_date,
            supervisor=supervisor,
            position=position,
            national_id=national_id,
            gender=gender,
            date_of_birth=date_of_birth,
            employment_status=employment_status,
            first_name=first_name_emp,
            last_name=last_name_emp,
            email=employee_email,
            phone=phone,
            address=address,
            # is_active is now auto-synced from employment_status
        )
        if cv_file is not None:
            with suppress(Exception):
                EmployeeDocument.objects.create(
                    employee=employee,
                    name=getattr(cv_file, "name", "cv.pdf"),
                    file=cv_file,
                )
        return employee
