from contextlib import suppress
from pathlib import Path
from typing import Any

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db import models
from django.utils.crypto import get_random_string
from PIL import Image
from PIL import UnidentifiedImageError
from rest_framework import serializers

from hr_payroll.employees.models import Contract
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument
from hr_payroll.employees.models import JobHistory
from hr_payroll.org.models import Department
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import Compensation
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.users.models import User
from hr_payroll.users.models import UserProfile

TOKEN_MAX_LEN = 128
MAX_PHOTO_MB = 5
MAX_DOC_MB = 15
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXTS = ALLOWED_IMAGE_EXTS | {".pdf", ".docx", ".xlsx"}


class SalaryComponentInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[
            ("base", "Base"),
            ("recurring", "Recurring"),
            ("one_off", "One-off"),
            ("offset", "Offset"),
        ]
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    label = serializers.CharField(required=False, allow_blank=True)


class EmployeeRegistrationSerializer(serializers.Serializer):
    # Users (General Tab)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    gender = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    nationality = serializers.CharField(required=False, allow_blank=True)
    health_care = serializers.CharField(required=False, allow_blank=True)
    marital_status = serializers.CharField(required=False, allow_blank=True)
    personal_tax_id = serializers.CharField(required=False, allow_blank=True)
    social_insurance = serializers.CharField(required=False, allow_blank=True)
    photo = serializers.ImageField(
        required=False,
        allow_null=True,
        help_text="Allowed: jpg, jpeg, png, webp. Max 5MB",
    )
    # Optional single document uploaded at registration
    document_name = serializers.CharField(required=False, allow_blank=True)
    document_file = serializers.FileField(
        required=False,
        allow_null=True,
        help_text="Allowed: pdf, docx, xlsx, jpg, jpeg, png, webp. Max 15MB",
    )

    # Employees (Job Tab)
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    office = serializers.CharField(required=False, allow_blank=True)
    time_zone = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    join_date = serializers.DateField(required=False, allow_null=True)
    last_working_date = serializers.DateField(required=False, allow_null=True)

    # Initial job history (first/current)
    job_effective_date = serializers.DateField(required=False, allow_null=True)
    job_position_type = serializers.CharField(required=False, allow_blank=True)
    job_employment_type = serializers.CharField(required=False, allow_blank=True)

    # Current contract
    contract_number = serializers.CharField(required=False, allow_blank=True)
    contract_name = serializers.CharField(required=False, allow_blank=True)
    contract_type = serializers.CharField(required=False, allow_blank=True)
    contract_start_date = serializers.DateField(required=False, allow_null=True)
    contract_end_date = serializers.DateField(required=False, allow_null=True)

    # Compensation components
    components = SalaryComponentInputSerializer(many=True, required=False)

    # Dependents list
    dependents = serializers.ListSerializer(
        child=serializers.DictField(), required=False
    )

    # Bank detail (optional)
    bank_name = serializers.CharField(required=False, allow_blank=True)
    branch = serializers.CharField(required=False, allow_blank=True)
    swift_bic = serializers.CharField(required=False, allow_blank=True)
    account_name = serializers.CharField(required=False, allow_blank=True)
    account_number = serializers.CharField(required=False, allow_blank=True)
    iban = serializers.CharField(required=False, allow_blank=True)

    # Optional fingerprint/device token to enroll during registration
    fingerprint_token = serializers.CharField(required=False, allow_blank=True)

    def _validate_image(self, f):
        if f is None:
            return f
        size_mb = (getattr(f, "size", 0) or 0) / (1024 * 1024)
        if size_mb > MAX_PHOTO_MB:
            msg = f"Image too large: {size_mb:.1f} MB > {MAX_PHOTO_MB} MB"
            raise serializers.ValidationError({"photo": [msg]})
        ext = Path(getattr(f, "name", "")).suffix
        if ext.lower() not in ALLOWED_IMAGE_EXTS:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTS))
            msg = f"Unsupported image type '{ext}'. Allowed: {allowed}"
            raise serializers.ValidationError({"photo": [msg]})
        try:
            # Pillow validation to ensure file is a real image
            Image.open(f).verify()
        except UnidentifiedImageError as exc:
            msg = "Invalid image file"
            raise serializers.ValidationError({"photo": [msg]}) from exc
        finally:
            with suppress(Exception):
                f.seek(0)
        return f

    def _validate_document(self, f, name: str | None = None):
        if f is None:
            return f
        size_mb = (getattr(f, "size", 0) or 0) / (1024 * 1024)
        if size_mb > MAX_DOC_MB:
            msg = f"File too large: {size_mb:.1f} MB > {MAX_DOC_MB} MB"
            raise serializers.ValidationError({"document_file": [msg]})
        filename = getattr(f, "name", "")
        ext = Path(filename).suffix
        if ext.lower() not in ALLOWED_DOC_EXTS:
            allowed = ", ".join(sorted(ALLOWED_DOC_EXTS))
            msg = f"Unsupported file type '{ext}'. Allowed: {allowed}"
            raise serializers.ValidationError({"document_file": [msg]})
        # For images, additionally validate with Pillow
        if ext.lower() in ALLOWED_IMAGE_EXTS:
            try:
                Image.open(f).verify()
            except UnidentifiedImageError as exc:
                msg = "Invalid image file"
                raise serializers.ValidationError({"document_file": [msg]}) from exc
            finally:
                with suppress(Exception):
                    f.seek(0)
        return f

    def validate_fingerprint_token(self, value: str) -> str:
        if not value:
            return value
        if Employee.objects.filter(fingerprint_token=value).exists():
            msg = "Fingerprint token already in use"
            raise serializers.ValidationError(msg)
        if len(value) > TOKEN_MAX_LEN:
            msg = f"Must be at most {TOKEN_MAX_LEN} characters"
            raise serializers.ValidationError(msg)
        return value

    def _generate_username(self, first_name: str, last_name: str) -> str:
        """Generate a unique username with a short salt to avoid collisions.

        Pattern: <first>.<last>-<salt>, lowercased, spaces removed. Salt is 4 chars.
        """
        base = (first_name + "." + last_name).lower().replace(" ", "") or "user"
        # Keep only url-safe chars
        base = "".join(ch for ch in base if ch.isalnum() or ch in {".", "-", "_"})
        while True:
            salt = get_random_string(
                4, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789"
            )
            candidate = f"{base}-{salt}"
            if not User.objects.filter(username=candidate).exists():
                return candidate

    def _email_domain(self) -> str:
        # Use a valid default domain; allow override from settings
        return getattr(settings, "GENERATED_EMAIL_DOMAIN", "example.com")

    def _generate_password(self) -> str:
        charset = (
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
        )
        return get_random_string(12, charset)

    def _generate_employee_id(self) -> str:
        # Very simple sequential pattern: E-<zero-padded>
        last = Employee.objects.order_by("-id").first()
        nxt = (last.id + 1) if last else 1
        return f"E-{nxt:05d}"

    def create(self, validated):  # noqa: C901 - orchestrates multiple related creates atomically
        # Create User with generated username/email/password
        first = validated.get("first_name", "").strip()
        last = validated.get("last_name", "").strip()
        if not first or not last:
            raise serializers.ValidationError(
                {"first_name": ["Required"], "last_name": ["Required"]}
            )

        username = self._generate_username(first, last)
        email = f"{username}@{self._email_domain()}"
        raw_password = self._generate_password()
        user = User.objects.create_user(
            username=username,
            email=email,
            password=raw_password,
            first_name=first,
            last_name=last,
        )

        # Create or update UserProfile
        UserProfile.objects.create(
            user=user,
            phone=validated.get("phone", ""),
            time_zone=validated.get("time_zone", ""),
            gender=validated.get("gender", ""),
            date_of_birth=validated.get("date_of_birth"),
            nationality=validated.get("nationality", ""),
            marital_status=validated.get("marital_status", ""),
            personal_tax_id=validated.get("personal_tax_id", ""),
            social_insurance=validated.get("social_insurance", ""),
        )

        # Create Employee
        emp = Employee.objects.create(
            user=user,
            title=validated.get("title", ""),
            department=validated.get("department_id"),
            time_zone=validated.get("time_zone", ""),
            office=validated.get("office", ""),
            join_date=validated.get("join_date"),
            last_working_date=validated.get("last_working_date"),
            is_active=True,
            health_care=validated.get("health_care", ""),
            fingerprint_token=(validated.get("fingerprint_token") or None),
        )
        # set photo if present (with validation)
        if validated.get("photo") is not None:
            self._validate_image(validated.get("photo"))
            emp.photo = validated.get("photo")
            emp.save(update_fields=["photo"])

        # Generate employee_id after we have pk
        emp.employee_id = self._generate_employee_id()
        emp.save(update_fields=["employee_id"])

        # Job history
        if validated.get("job_effective_date"):
            JobHistory.objects.create(
                employee=emp,
                effective_date=validated.get("job_effective_date"),
                job_title=validated.get("title", ""),
                position_type=validated.get("job_position_type", ""),
                employment_type=validated.get("job_employment_type", ""),
                line_manager=None,
            )

        # Contract creation
        if validated.get("contract_number") and validated.get("contract_start_date"):
            Contract.objects.create(
                employee=emp,
                contract_number=validated.get("contract_number"),
                contract_name=validated.get("contract_name", ""),
                contract_type=validated.get("contract_type", ""),
                start_date=validated.get("contract_start_date"),
                end_date=validated.get("contract_end_date"),
            )

        # Compensation components
        comps = validated.get("components") or []
        if comps:
            comp = Compensation.objects.create(employee=emp)
            for c in comps:
                SalaryComponent.objects.create(
                    compensation=comp,
                    kind=c["kind"],
                    amount=c["amount"],
                    label=c.get("label", ""),
                )
            comp.recalc_total()

        # Dependents
        for d in validated.get("dependents", []) or []:
            name = d.get("name")
            if not name:
                continue
            Dependent.objects.create(
                employee=emp,
                name=name,
                relationship=d.get("relationship", ""),
                date_of_birth=d.get("date_of_birth"),
            )

        # Bank detail
        if validated.get("bank_name") or validated.get("account_number"):
            BankDetail.objects.create(
                employee=emp,
                bank_name=validated.get("bank_name", ""),
                branch=validated.get("branch", ""),
                swift_bic=validated.get("swift_bic", ""),
                account_name=validated.get("account_name", ""),
                account_number=validated.get("account_number", ""),
                iban=validated.get("iban", ""),
            )

        # Single document (if provided)
        doc_file = validated.get("document_file")
        if doc_file is not None:
            self._validate_document(doc_file, validated.get("document_name"))
            doc_name = (
                validated.get("document_name") or doc_file.name or "Document"
            ).strip()
            EmployeeDocument.objects.create(employee=emp, name=doc_name, file=doc_file)

        # Mark email as verified and primary in allauth
        EmailAddress.objects.get_or_create(
            user=user, email=email, defaults={"verified": True, "primary": True}
        )

        # Record credentials on serializer for response
        self.created_credentials = {
            "username": username,
            "email": email,
            "password": raw_password,
        }
        return emp


class EmployeeReadSerializer(serializers.ModelSerializer):
    # Enriched read: pull data from related models to match UI detail
    id = serializers.SerializerMethodField()
    full_name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.profile.phone", read_only=True)
    timezone = serializers.CharField(source="time_zone", read_only=True)
    department = serializers.CharField(source="department.name", read_only=True)
    employment_type = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="title", read_only=True)
    status = serializers.SerializerMethodField()
    position = serializers.CharField(source="title", read_only=True)
    gender = serializers.CharField(source="user.profile.gender", read_only=True)
    date_of_birth = serializers.DateField(
        source="user.profile.date_of_birth", read_only=True
    )
    nationality = serializers.CharField(
        source="user.profile.nationality", read_only=True
    )
    marital_status = serializers.CharField(
        source="user.profile.marital_status", read_only=True
    )
    personal_tax_id = serializers.CharField(
        source="user.profile.personal_tax_id", read_only=True
    )
    social_insurance = serializers.CharField(
        source="user.profile.social_insurance", read_only=True
    )
    total_compensation = serializers.SerializerMethodField()
    salary = serializers.SerializerMethodField()
    recurring = serializers.SerializerMethodField()
    one_off = serializers.SerializerMethodField()
    offset = serializers.SerializerMethodField()
    job_history = serializers.SerializerMethodField()
    contracts = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id",
            "photo",
            "full_name",
            "position",
            "status",
            "email",
            "phone",
            "timezone",
            "department",
            "office",
            "line_manager",
            "gender",
            "date_of_birth",
            "nationality",
            "health_care",
            "marital_status",
            "personal_tax_id",
            "social_insurance",
            "employee_id",
            "join_date",
            "service_years",
            "job_history",
            "contracts",
            "employment_type",
            "job_title",
            "last_working_date",
            "total_compensation",
            "salary",
            "recurring",
            "one_off",
            "offset",
            "documents",
        ]

    # Derived and passthrough helpers
    def get_id(self, obj) -> str:
        return str(obj.pk)

    @property
    def _latest_comp(self):
        def _inner(emp):
            return (
                getattr(emp, "compensations", None).order_by("-created_at").first()
                if hasattr(emp, "compensations")
                else None
            )

        return _inner

    def get_total_compensation(self, obj) -> str:
        comp = self._latest_comp(obj)
        return f"{getattr(comp, 'total_compensation', 0) or 0:.2f}" if comp else "0.00"

    def _sum_components(self, obj, kind: str) -> str:
        comp = self._latest_comp(obj)
        if not comp:
            return "0.00"
        total = (
            comp.components.filter(kind=kind)
            .aggregate(models.Sum("amount"))
            .get("amount__sum")
            or 0
        )
        return f"{total:.2f}"

    def get_salary(self, obj) -> str:
        return self._sum_components(obj, "base")

    def get_recurring(self, obj) -> str:
        return self._sum_components(obj, "recurring")

    def get_one_off(self, obj) -> str:
        return self._sum_components(obj, "one_off")

    def get_offset(self, obj) -> str:
        return self._sum_components(obj, "offset")

    def get_status(self, obj) -> str:
        return "Active" if obj.is_active else "Inactive"

    def get_employment_type(self, obj) -> str:
        latest = obj.job_history.order_by("-effective_date", "-pk").first()
        return getattr(latest, "employment_type", "") if latest else ""

    def get_job_history(self, obj) -> list[dict[str, Any]]:
        return [  # pragma: no cover - formatting only
            {
                "id": j.pk,
                "effective_date": j.effective_date.isoformat(),
                "job_title": j.job_title,
                "position_type": j.position_type,
                "employment_type": j.employment_type,
            }
            for j in obj.job_history.order_by("effective_date", "pk")
        ]

    def get_contracts(self, obj) -> list[dict[str, Any]]:
        return [  # pragma: no cover - formatting only
            {
                "id": c.pk,
                "contract_number": c.contract_number,
                "contract_name": c.contract_name,
                "contract_type": c.contract_type,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat() if c.end_date else None,
            }
            for c in obj.contracts.order_by("start_date", "pk")
        ]

    def get_documents(self, obj) -> list[dict[str, Any]]:
        return [  # pragma: no cover - formatting only
            {
                "id": d.pk,
                "name": d.name,
                "uploaded_at": d.uploaded_at.isoformat(),
                "file": getattr(d.file, "url", ""),
            }
            for d in obj.documents.order_by("-uploaded_at")
        ]


class EmployeeUpdateSerializer(serializers.ModelSerializer):
    # Allow updating core employee fields only; map *_id for convenience
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
        source="department",
    )
    line_manager_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        required=False,
        allow_null=True,
        source="line_manager",
    )

    class Meta:
        model = Employee
        fields = [
            "photo",
            "time_zone",
            "office",
            "title",
            "join_date",
            "last_working_date",
            "is_active",
            "health_care",
            "department_id",
            "line_manager_id",
        ]

    def validate_photo(self, f):
        if f is None:
            return f
        size_mb = (getattr(f, "size", 0) or 0) / (1024 * 1024)
        if size_mb > MAX_PHOTO_MB:
            msg = f"Image too large: {size_mb:.1f} MB > {MAX_PHOTO_MB} MB"
            raise serializers.ValidationError(msg)
        ext = Path(getattr(f, "name", "")).suffix
        if ext.lower() not in ALLOWED_IMAGE_EXTS:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTS))
            msg = f"Unsupported image type '{ext}'. Allowed: {allowed}"
            raise serializers.ValidationError(msg)
        try:
            Image.open(f).verify()
        except UnidentifiedImageError as exc:
            msg = "Invalid image file"
            raise serializers.ValidationError(msg) from exc
        finally:
            with suppress(Exception):
                f.seek(0)
        return f
