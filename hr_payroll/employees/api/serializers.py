"""Serializers for Employees API."""

import logging
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from PIL import Image
from PIL.Image import UnidentifiedImageError
from rest_framework import serializers

from hr_payroll.employees.models import Contract
from hr_payroll.employees.models import EmergencyContact
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeAddress
from hr_payroll.employees.models import EmployeeDocument
from hr_payroll.employees.models import JobHistory
from hr_payroll.org.models import Department
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.policies import get_policy_document
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
    # Alias for frontend compatibility
    documents = serializers.FileField(
        required=False,
        allow_null=True,
        source="document_file",
        help_text="Alias for document_file",
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

    # Shift Assignment
    current_shift = serializers.CharField(required=False, allow_blank=True)

    # Compensation components (legacy list support)
    components = SalaryComponentInputSerializer(many=True, required=False)
    # Compensation flat fields (Frontend Adapter)
    salary = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    offset = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    one_off = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )

    # Dependents list
    dependents = serializers.ListSerializer(
        child=serializers.DictField(), required=False
    )

    # Address
    primary_address = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(
        required=False, allow_blank=True
    )  # Frontend sends 'state'
    city = serializers.CharField(required=False, allow_blank=True)
    postcode = serializers.CharField(
        required=False, allow_blank=True
    )  # Frontend sends 'postcode'

    # Emergency Contact (Frontend sends emefullname, etc.)
    emergency_full_name = serializers.CharField(
        required=False, allow_blank=True, source="emefullname"
    )
    emergency_phone = serializers.CharField(
        required=False, allow_blank=True, source="emephonenumber"
    )
    emergency_state = serializers.CharField(
        required=False, allow_blank=True, source="emestate"
    )
    emergency_city = serializers.CharField(
        required=False, allow_blank=True, source="emecity"
    )
    emergency_postcode = serializers.CharField(
        required=False, allow_blank=True, source="emepostcode"
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

            def _raise_photo_ext_error(extension: str, allowed_exts: str) -> None:
                raise serializers.ValidationError(
                    {
                        "photo": [
                            (
                                "Unsupported image type "
                                f"'{extension}'. Allowed: {allowed_exts}"
                            )
                        ]
                    }
                )

            _raise_photo_ext_error(ext, allowed)
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
        # Load rule from Recruitment Policy (Org ID 1 hardcoded for now)
        policy = get_policy_document(org_id=1)
        recruitment = policy.get("recruitmentPolicy", {})
        onboarding = recruitment.get("onboarding", {})

        # Defaults
        prefix = "E-"

        if onboarding.get("idPrefix"):
            prefix = onboarding["idPrefix"].strip().upper()

        # Sequential Generation
        last = Employee.objects.order_by("-id").first()
        nxt = (last.id + 1) if last else 1
        return f"{prefix}{nxt:05d}"

    def _create_user_and_profile(self, validated):
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

        # Mark email as verified and primary in allauth
        EmailAddress.objects.get_or_create(
            user=user, email=email, defaults={"verified": True, "primary": True}
        )

        return user, username, email, raw_password

    def _create_contract_record(self, emp, validated):
        if validated.get("contract_number") and validated.get("contract_start_date"):
            c_start = validated.get("contract_start_date")
            c_end = validated.get("contract_end_date")
            c_type = validated.get("contract_type", "").lower()

            # Apply Probation Policy if type is probation and end date is missing
            if "probation" in c_type and not c_end:
                policy = get_policy_document(org_id=1)
                probation_months = policy.get("probationPolicy", {}).get(
                    "durationMonths"
                )
                if probation_months and isinstance(probation_months, int):
                    from dateutil.relativedelta import relativedelta

                    c_end = c_start + relativedelta(months=probation_months)

            Contract.objects.create(
                employee=emp,
                contract_number=validated.get("contract_number"),
                contract_name=validated.get("contract_name", ""),
                contract_type=validated.get("contract_type", ""),
                start_date=c_start,
                end_date=c_end,
            )

    def _create_salary_structure(self, emp, validated):
        comps = validated.get("components") or []
        if validated.get("salary"):
            comps.append(
                {"kind": "base", "amount": validated["salary"], "label": "Base Salary"}
            )
        if validated.get("offset"):
            comps.append(
                {"kind": "offset", "amount": validated["offset"], "label": "Offset"}
            )
        if validated.get("one_off"):
            comps.append(
                {
                    "kind": "one_off",
                    "amount": validated["one_off"],
                    "label": "Sign-on Bonus",
                }
            )

        if comps:
            structure = EmployeeSalaryStructure.objects.create(
                employee=emp,
                base_salary=Decimal("0.00"),  # Will be calculated from components
            )
            total_base = Decimal("0.00")
            for c in comps:
                component, _ = SalaryComponent.objects.get_or_create(
                    name=c.get("label") or f"{c['kind']} component",
                    defaults={
                        "component_type": "earning",
                        "is_recurring": c["kind"] in ["base", "recurring"],
                        "is_taxable": True,
                    },
                )
                SalaryStructureItem.objects.create(
                    structure=structure, component=component, amount=c["amount"]
                )
                if c["kind"] == "base":
                    total_base += c["amount"]
            structure.base_salary = total_base
            structure.save(update_fields=["base_salary"])

    def _create_bank_and_dependents(self, emp, validated):
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

        if validated.get("bank_name") or validated.get("account_number"):
            bank_name = validated.get("bank_name", "").strip()
            if bank_name:
                bank, _ = BankMaster.objects.get_or_create(
                    name=bank_name,
                    defaults={
                        "swift_code": validated.get("swift_bic", ""),
                        "code": "",
                    },
                )
                BankDetail.objects.create(
                    employee=emp,
                    bank=bank,
                    branch_name=validated.get("branch", ""),
                    account_holder=validated.get("account_name", "") or emp.user.name,
                    account_number=validated.get("account_number", ""),
                    iban=validated.get("iban", ""),
                )

    def _create_addresses_contacts(self, emp, validated):
        if any(validated.get(k) for k in ["primary_address", "city", "country"]):
            EmployeeAddress.objects.create(
                employee=emp,
                primary_address=validated.get("primary_address", ""),
                country=validated.get("country", ""),
                state_province=validated.get("state", ""),
                city=validated.get("city", ""),
                postal_code=validated.get("postcode", ""),
            )

        if validated.get("emefullname"):
            EmergencyContact.objects.create(
                employee=emp,
                full_name=validated.get("emefullname", ""),
                phone_number=validated.get("emephonenumber", ""),
                state_province=validated.get("emestate", ""),
                city=validated.get("emecity", ""),
                postal_code=validated.get("emepostcode", ""),
            )

    def create(self, validated):
        user, username, email, raw_password = self._create_user_and_profile(validated)

        department = validated.get("department_id")
        line_manager = None
        if department and department.manager:
            line_manager = department.manager

        emp = Employee.objects.create(
            user=user,
            title=validated.get("title", ""),
            department=department,
            line_manager=line_manager,
            time_zone=validated.get("time_zone", ""),
            office=validated.get("office", ""),
            current_shift=validated.get("current_shift", ""),
            join_date=validated.get("join_date"),
            last_working_date=validated.get("last_working_date"),
            is_active=True,
            health_care=validated.get("health_care", ""),
            fingerprint_token=(validated.get("fingerprint_token") or None),
        )
        if validated.get("photo") is not None:
            self._validate_image(validated.get("photo"))
            emp.photo = validated.get("photo")
            emp.save(update_fields=["photo"])

        emp.employee_id = self._generate_employee_id()
        emp.save(update_fields=["employee_id"])

        if validated.get("job_effective_date"):
            JobHistory.objects.create(
                employee=emp,
                effective_date=validated.get("job_effective_date"),
                job_title=validated.get("title", ""),
                position_type=validated.get("job_position_type", ""),
                employment_type=validated.get("job_employment_type", ""),
                line_manager=line_manager,
            )

        self._create_contract_record(emp, validated)
        self._create_addresses_contacts(emp, validated)
        self._create_salary_structure(emp, validated)
        self._create_bank_and_dependents(emp, validated)

        doc_file = validated.get("document_file")
        if doc_file is not None:
            self._validate_document(doc_file, validated.get("document_name"))
            doc_name = (
                validated.get("document_name") or doc_file.name or "Document"
            ).strip()
            EmployeeDocument.objects.create(employee=emp, name=doc_name, file=doc_file)

        self.created_credentials = {
            "username": username,
            "email": email,
            "password": raw_password,
        }
        return emp


class EmployeeReadSerializer(serializers.ModelSerializer):
    # Enriched read: organized into frontend-friendly nested structure
    id = serializers.SerializerMethodField()
    general = serializers.SerializerMethodField()
    job = serializers.SerializerMethodField()
    payroll = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "general", "job", "payroll", "documents"]

    def get_id(self, obj) -> str:
        return str(obj.pk)

    def get_general(self, obj) -> dict[str, Any]:
        profile = getattr(obj.user, "profile", None)
        return {
            "fullname": obj.user.name or "",
            "gender": getattr(profile, "gender", "") if profile else "",
            "dateofbirth": (
                profile.date_of_birth.isoformat()
                if profile and profile.date_of_birth
                else ""
            ),
            "maritalstatus": getattr(profile, "marital_status", "") if profile else "",
            "nationality": getattr(profile, "nationality", "") if profile else "",
            "personaltaxid": getattr(profile, "personal_tax_id", "") if profile else "",
            "emailaddress": obj.user.email or "",
            "socialinsurance": getattr(profile, "social_insurance", "")
            if profile
            else "",
            "healthinsurance": obj.health_care or "",
            "phonenumber": getattr(profile, "phone", "") if profile else "",
            "photo": obj.photo.url if obj.photo else "",
        }

    def get_job(self, obj) -> dict[str, Any]:
        latest_job = obj.job_history.order_by("-effective_date", "-pk").first()
        latest_contract = obj.contracts.order_by("-start_date", "-pk").first()

        service_days = (
            (timezone.localdate() - obj.join_date).days if obj.join_date else 0
        )
        return {
            "employeeid": obj.employee_id or "",
            "serviceyear": f"{service_days // 365}",
            "joindate": obj.join_date.isoformat() if obj.join_date else "",
            "jobtitle": obj.title or "",
            "positiontype": (
                getattr(latest_job, "position_type", "") if latest_job else ""
            ),
            "employmenttype": (
                getattr(latest_job, "employment_type", "") if latest_job else ""
            ),
            "linemanager": (obj.line_manager.user.name if obj.line_manager else ""),
            "contractnumber": (
                getattr(latest_contract, "contract_number", "")
                if latest_contract
                else ""
            ),
            "contractname": (
                getattr(latest_contract, "contract_name", "") if latest_contract else ""
            ),
            "contracttype": (
                getattr(latest_contract, "contract_type", "") if latest_contract else ""
            ),
            "startdate": (
                latest_contract.start_date.isoformat()
                if latest_contract and latest_contract.start_date
                else ""
            ),
            "enddate": (
                latest_contract.end_date.isoformat()
                if latest_contract and latest_contract.end_date
                else ""
            ),
            "department": obj.department.name if obj.department else "",
            "office": obj.office or "",
            "timezone": obj.time_zone or "",
            "shift": obj.current_shift or "",
        }

    def get_payroll(self, obj) -> dict[str, Any]:
        latest_job = obj.job_history.order_by("-effective_date", "-pk").first()
        comp = (
            getattr(obj, "compensations", None).order_by("-created_at").first()
            if hasattr(obj, "compensations")
            else None
        )

        def _sum_components(kind: str) -> str:
            if not comp:
                return "0.00"
            total = (
                comp.components.filter(kind=kind)
                .aggregate(models.Sum("amount"))
                .get("amount__sum")
                or 0
            )
            return f"{total:.2f}"

        return {
            "employeestatus": "Active" if obj.is_active else "Inactive",
            "employmenttype": (
                getattr(latest_job, "employment_type", "") if latest_job else ""
            ),
            "jobdate": obj.join_date.isoformat() if obj.join_date else "",
            "lastworkingdate": (
                obj.last_working_date.isoformat() if obj.last_working_date else ""
            ),
            "salary": _sum_components("base"),
            "offset": _sum_components("offset"),
            "recurring": _sum_components("recurring"),
        }

    def get_documents(self, obj) -> dict[str, Any]:
        request = self.context.get("request")
        return {
            "files": [
                {
                    "id": d.id,
                    "name": d.name,
                    "url": (
                        request.build_absolute_uri(d.file.url)
                        if request and d.file
                        else getattr(d.file, "url", "")
                    ),
                    "blob_url": (
                        request.build_absolute_uri(
                            f"/api/v1/employees/serve-document/{d.id}/"
                        )
                        if request
                        else f"/api/v1/employees/serve-document/{d.id}/"
                    ),
                }
                for d in obj.documents.order_by("-uploaded_at")
            ]
        }


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
            "current_shift",
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


class EmployeeNestedUpdateSerializer(serializers.Serializer):
    """Accept nested employee updates matching EmployeeReadSerializer output."""

    general = serializers.DictField(required=False, allow_null=True)
    job = serializers.DictField(required=False, allow_null=True)
    payroll = serializers.DictField(required=False, allow_null=True)

    def _ensure_profile(self, user):
        """Ensure UserProfile exists for the user."""
        profile = getattr(user, "profile", None)
        if not profile:
            profile = UserProfile.objects.create(user=user)
            logging.warning(
                "UserProfile did not exist for user %s, created new profile",
                user.id,
            )
        return profile

    def _update_user_fields(self, user, general, updated_fields):
        """Update user-level fields (fullname, email)."""
        if general.get("fullname"):
            parts = general["fullname"].strip().split(maxsplit=1)
            user.first_name = parts[0] if parts else ""
            user.last_name = parts[1] if len(parts) > 1 else ""
            user.save()
            updated_fields.append("fullname")
            logging.info("Updated fullname: %s %s", user.first_name, user.last_name)

        if general.get("emailaddress"):
            user.email = general["emailaddress"]
            user.save()
            updated_fields.append("emailaddress")
            logging.info("Updated email: %s", user.email)

    def _update_profile_fields(self, profile, instance, general, updated_fields):
        """Update UserProfile fields."""
        if "dateofbirth" in general:
            if general["dateofbirth"]:
                try:
                    profile.date_of_birth = datetime.fromisoformat(
                        general["dateofbirth"]
                    ).date()
                    updated_fields.append("dateofbirth")
                    logging.info("Updated date_of_birth: %s", profile.date_of_birth)
                except (ValueError, AttributeError) as e:
                    logging.warning(
                        "Invalid dateofbirth format: %s, error: %s",
                        general["dateofbirth"],
                        e,
                    )
            else:
                profile.date_of_birth = None
                updated_fields.append("dateofbirth (cleared)")
                logging.info("Cleared date_of_birth")

        fields_map = {
            "healthinsurance": ("health_care", instance),
            "gender": ("gender", profile),
            "maritalstatus": ("marital_status", profile),
            "nationality": ("nationality", profile),
            "personaltaxid": ("personal_tax_id", profile),
            "socialinsurance": ("social_insurance", profile),
            "phonenumber": ("phone", profile),
        }

        for key, (attr, obj) in fields_map.items():
            if key in general:
                value = general[key] or ""
                setattr(obj, attr, value)
                updated_fields.append(key)
                logging.info("Updated %s: '%s'", attr, value)

        profile.save()
        logging.info("UserProfile saved successfully")

    def _update_job_fields(self, instance, job, updated_fields):
        """Update job-related fields."""
        if "jobtitle" in job:
            instance.title = job["jobtitle"]
            updated_fields.append("jobtitle")
        if "office" in job:
            instance.office = job["office"]
            updated_fields.append("office")
        if "timezone" in job:
            instance.time_zone = job["timezone"]
            updated_fields.append("timezone")
        if "shift" in job:
            instance.current_shift = job["shift"]
            updated_fields.append("current_shift")
        if "joindate" in job:
            if job["joindate"]:
                try:
                    instance.join_date = datetime.fromisoformat(job["joindate"]).date()
                    updated_fields.append("joindate")
                except (ValueError, AttributeError) as e:
                    logging.warning(
                        "Invalid joindate format: %s, error: %s",
                        job["joindate"],
                        e,
                    )
            else:
                instance.join_date = None
                updated_fields.append("joindate (cleared)")

    def _update_payroll_fields(self, instance, payroll, updated_fields):
        """Update payroll-related fields."""
        if "employeestatus" in payroll:
            instance.is_active = payroll["employeestatus"] == "Active"
            updated_fields.append("employeestatus")
        if "lastworkingdate" in payroll:
            if payroll["lastworkingdate"]:
                try:
                    instance.last_working_date = datetime.fromisoformat(
                        payroll["lastworkingdate"]
                    ).date()
                    updated_fields.append("lastworkingdate")
                except (ValueError, AttributeError) as e:
                    logging.warning(
                        "Invalid lastworkingdate format: %s, error: %s",
                        payroll["lastworkingdate"],
                        e,
                    )
            else:
                instance.last_working_date = None
                updated_fields.append("lastworkingdate (cleared)")

    def update(self, instance, validated_data):
        """Update employee instance with validated data."""
        logging.info(
            "EmployeeNestedUpdateSerializer.update called for employee %s",
            instance.id,
        )
        logging.info("Received data sections: %s", list(validated_data.keys()))

        user = instance.user
        profile = self._ensure_profile(user)
        updated_fields = []

        general = validated_data.get("general", {})
        if general:
            logging.info(
                "Processing 'general' section with fields: %s",
                list(general.keys()),
            )
            self._update_user_fields(user, general, updated_fields)
            self._update_profile_fields(profile, instance, general, updated_fields)

        job = validated_data.get("job", {})
        if job:
            logging.info("Processing 'job' section with fields: %s", list(job.keys()))
            self._update_job_fields(instance, job, updated_fields)

        payroll = validated_data.get("payroll", {})
        if payroll:
            logging.info(
                "Processing 'payroll' section with fields: %s",
                list(payroll.keys()),
            )
            self._update_payroll_fields(instance, payroll, updated_fields)

        # Handle profile photo updates sent as multipart file
        # Accept both 'photo' (preferred) and legacy 'image' keys
        def _raise_photo_ext_error(extension: str, allowed: str) -> None:
            raise serializers.ValidationError(
                {
                    "photo": [
                        (f"Unsupported image type '{extension}'. Allowed: {allowed}")
                    ]
                }
            )

        request = self.context.get("request")
        try:
            files = getattr(request, "FILES", {}) if request else {}
            photo_file = files.get("photo") or files.get("image")
            if photo_file is not None:
                # Basic validation (aligns with registration rules)
                ext = Path(getattr(photo_file, "name", "")).suffix.lower()
                if ext and ext not in ALLOWED_IMAGE_EXTS:
                    allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTS))
                    _raise_photo_ext_error(ext, allowed)
                try:
                    Image.open(photo_file).verify()
                except UnidentifiedImageError as exc:
                    raise serializers.ValidationError(
                        {"photo": ["Invalid image file"]}
                    ) from exc
                finally:
                    with suppress(Exception):
                        photo_file.seek(0)

                instance.photo = photo_file
                instance.save(update_fields=["photo"])
                updated_fields.append("photo")
                logging.info("Updated photo for employee %s", instance.id)
        except serializers.ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - defensive logging only
            logging.warning("Photo update skipped due to error: %s", exc)

        instance.save()
        logging.info(
            "Employee %s saved successfully. Updated fields: %s",
            instance.id,
            updated_fields,
        )
        return instance


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    """Serializer for EmployeeDocument model."""

    class Meta:
        model = EmployeeDocument
        fields = ["id", "employee", "name", "file", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at", "employee"]

    def validate_file(self, f):
        """Validate uploaded file."""
        # reuse logic from EmployeeRegistrationSerializer or similar if needed
        # For now, basic validation
        return f


class EmployeeSearchSerializer(serializers.ModelSerializer):
    """Minimal projection for employee search suggestions."""

    name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    employeeid = serializers.CharField(source="employee_id", allow_blank=True)

    class Meta:
        model = Employee
        fields = ["id", "name", "photo", "email", "employeeid"]

    def get_name(self, obj) -> str:
        user = getattr(obj, "user", None)
        return getattr(user, "name", "") or ""

    def get_email(self, obj) -> str:
        user = getattr(obj, "user", None)
        return getattr(user, "email", "") or ""

    def get_photo(self, obj) -> str:
        request = (
            self.context.get("request") if isinstance(self.context, dict) else None
        )
        if not obj.photo:
            return ""
        url = getattr(obj.photo, "url", "")
        if not url:
            return ""
        if request is not None:
            with suppress(Exception):
                return request.build_absolute_uri(url)
        return url
