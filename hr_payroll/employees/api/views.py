import logging
import os
import secrets
from contextlib import suppress

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.api.permissions import IsAdminOrManagerCanWrite
from hr_payroll.employees.api.serializers import CVParsedDataSerializer
from hr_payroll.employees.api.serializers import CVParseUploadSerializer
from hr_payroll.employees.api.serializers import DepartmentSerializer
from hr_payroll.employees.api.serializers import EmployeeDocumentSerializer
from hr_payroll.employees.api.serializers import EmployeeSerializer
from hr_payroll.employees.api.serializers import OnboardEmployeeExistingSerializer
from hr_payroll.employees.api.serializers import OnboardEmployeeNewSerializer
from hr_payroll.employees.api.serializers import _generate_secure_password
from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument
from hr_payroll.employees.services.cv_parser import parse_cv as do_parse

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(tags=["Departments"]),
    retrieve=extend_schema(tags=["Departments"]),
    create=extend_schema(tags=["Departments"]),
    update=extend_schema(tags=["Departments"]),
    partial_update=extend_schema(tags=["Departments"]),
    destroy=extend_schema(tags=["Departments"]),
)
class DepartmentViewSet(viewsets.ModelViewSet[Department]):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated & IsAdminOrManagerCanWrite]

    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()
        request = getattr(self, "request", None)
        include_inactive = False
        if request is not None:
            u = request.user
            is_elevated = getattr(u, "is_staff", False) or (
                getattr(u, "groups", None)
                and u.groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            include_inactive = is_elevated and request.query_params.get(
                "include_inactive"
            ) in {"1", "true", "True"}
        return qs if include_inactive else qs.filter(is_active=True)


@extend_schema_view(
    list=extend_schema(tags=["Employees"]),
    retrieve=extend_schema(tags=["Employees"]),
)
class EmployeeViewSet(viewsets.ReadOnlyModelViewSet[Employee]):
    queryset = Employee.objects.select_related("user", "department")
    serializer_class = EmployeeSerializer
    # Authenticated users can read (limited by queryset), only elevated can write
    permission_classes = [IsAdminOrManagerCanWrite]

    def get_serializer_class(self):
        if getattr(self, "action", None) == "parse_cv":
            return CVParseUploadSerializer
        if getattr(self, "action", None) == "onboard_new":
            return OnboardEmployeeNewSerializer
        if getattr(self, "action", None) == "onboard_existing":
            return OnboardEmployeeExistingSerializer
        return super().get_serializer_class()

    def get_serializer(self, *args, **kwargs):  # type: ignore[override]
        # Use default serializer construction; dynamic initial values are
        # provided via context from get_serializer_context()
        return super().get_serializer(*args, **kwargs)

    def get_serializer_context(self):  # type: ignore[override]
        ctx = super().get_serializer_context()
        # Provide prefill values to the serializer for browsable API GET form
        if (
            getattr(self, "action", None) == "onboard_new"
            and getattr(self.request, "method", "").upper() == "GET"
        ):
            token = self.request.query_params.get("prefill_token")
            if token:
                data = cache.get(f"onboarding:prefill:{token}") or {}
                if isinstance(data, dict):
                    initial = self._build_prefill_initial(data)
                    if initial:
                        cv_dbg = (
                            getattr(settings, "DEBUG", False)
                            or os.environ.get("ENABLE_CV_DEBUG") == "1"
                        )
                        if cv_dbg:
                            logger.info(
                                "Onboard(new) prefill initial keys: %s",
                                sorted(initial.keys()),
                            )
                        ctx["prefill_initial"] = initial
        return ctx

    @staticmethod
    def _build_prefill_initial(data: dict) -> dict:
        """Map cached prefill data to serializer initial values.

        Accepts a dict with potential keys from CV parsing and returns
        a dict suitable for serializer initial values.
        """
        mapping = {
            "first_name": "first_name",
            "last_name": "last_name",
            "full_name": "full_name",
            "email": "employee_email",
            "phone": "phone",
            "date_of_birth": "date_of_birth",
            "address": "address",
        }
        initial: dict = {}
        for src, dest in mapping.items():
            val = data.get(src)
            if val:
                initial[dest] = val
        return initial

    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()
        request = self.request
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        include_inactive = is_elevated and request.query_params.get(
            "include_inactive"
        ) in {"1", "true", "True"}
        qs = qs if include_inactive else qs.filter(is_active=True)
        if is_elevated:
            return qs
        # Regular employees: only see their own record (and active by default)
        return qs.filter(user=u)

    # Creation is supported only via explicit onboarding endpoints below

    @extend_schema(
        summary="Parse a CV (PDF) and return extracted fields",
        description=(
            "Upload a CV as multipart/form-data with 'cv_file'. The service returns "
            "a best-effort extraction (first/last name, email, phone, date of birth, "
            "etc.) to prefill the onboarding form."
        ),
        request=CVParseUploadSerializer,
        responses={200: OpenApiResponse(response=CVParsedDataSerializer)},
        examples=[
            OpenApiExample(
                "Sample request",
                value={"cv_file": "<PDF binary>"},
                request_only=True,
            ),
            OpenApiExample(
                "Sample response",
                value={
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": "jane.doe@example.com",
                    "phone": "+15551234567",
                    "date_of_birth": "1990-06-15",
                },
                response_only=True,
            ),
        ],
    )
    @action(methods=["post"], detail=False, url_path="cv/parse")
    def parse_cv(self, request):
        # Only Admin/Manager should use parsing for onboarding
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can parse CVs for onboarding."
            raise PermissionDenied(msg)
        ser = CVParseUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        f = ser.validated_data["cv_file"]
        content = f.read()
        # Reset pointer in case caller wants to reuse; not required here
        with suppress(Exception):
            f.seek(0)

        extracted = do_parse(content, getattr(f, "name", None))
        # Ensure a dict is always returned
        if not isinstance(extracted, dict):
            extracted = {}
        # Store extracted data in cache with a short TTL for prefill
        token = secrets.token_urlsafe(16)
        ttl_minutes = getattr(settings, "ONBOARDING_PREFILL_TTL_MINUTES", 10)
        cache_key = f"onboarding:prefill:{token}"
        cache.set(cache_key, extracted, timeout=ttl_minutes * 60)

        # Redirect logic: if HTML renderer, or the client asked for redirect via
        # query param (?redirect=1), or the Accept header prefers text/html.
        next_path = f"/api/v1/employees/onboard/new/?prefill_token={token}"
        wants_redirect = False
        renderer = getattr(request, "accepted_renderer", None)
        if renderer is not None and getattr(renderer, "format", "") == "html":
            wants_redirect = True
        if request.query_params.get("redirect") in {"1", "true", "True"}:
            wants_redirect = True
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            wants_redirect = True

        if wants_redirect:
            resp = Response(status=status.HTTP_303_SEE_OTHER)
            resp["Location"] = next_path
            return resp

        # Otherwise, return the token and next URL along with extracted data
        return Response(
            {
                "prefill_token": token,
                "next": next_path,
                "extracted": extracted,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Onboard a brand-new employee (create User + Employee)",
        description=(
            "Creates a new active User (email marked verified) and the "
            "corresponding Employee. Only Admin or Manager may call this "
            "endpoint."
        ),
        examples=[
            OpenApiExample(
                "Minimal",
                value={
                    "first_name": "John",
                    "last_name": "Doe",
                    "department": 1,
                    "title": "Software Engineer",
                    "hire_date": "2025-10-01",
                },
            ),
            OpenApiExample(
                "Full",
                value={
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "department": 2,
                    "title": "HR Manager",
                    "hire_date": "2025-10-01",
                    "supervisor": 5,
                    "position": 3,
                    "national_id": "ID-123456",
                    "gender": "female",
                    "date_of_birth": "1990-06-15",
                    "employment_status": "active",
                    "employee_email": "jane.smith@company.com",
                    "phone": "+11234567890",
                    "address": "123 Main St",
                },
            ),
            OpenApiExample(
                "With CV upload (multipart)",
                summary="Use multipart/form-data with 'cv_file' field (PDF)",
                value={
                    "first_name": "Pat",
                    "last_name": "Lee",
                    "department": 1,
                    "cv_file": "<PDF binary>",
                },
            ),
        ],
        responses={
            201: OpenApiResponse(
                response=EmployeeSerializer,
                description="Employee created",
            ),
        },
    )
    @action(methods=["get", "post"], detail=False, url_path="onboard/new")
    def onboard_new(self, request):
        # Only elevated can onboard
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can onboard employees."
            raise PermissionDenied(msg)
        # If GET, prefill the form for browsable API using a token
        # stored by parse_cv
        if request.method.lower() == "get":
            # Browsable API will render the form with initial values
            # provided by get_serializer
            self.get_serializer()  # trigger serializer construction with initial
            return Response(
                {"detail": "Submit the form to create the employee."},
                status=status.HTTP_200_OK,
            )

        serializer = OnboardEmployeeNewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        emp_data = EmployeeSerializer(employee, context={"request": request}).data
        # Attach generated credentials separately under a new key
        # to avoid field duplication
        creds = {}
        if hasattr(serializer, "generated_username"):
            creds["username"] = serializer.generated_username
        if hasattr(serializer, "generated_email"):
            creds["email"] = serializer.generated_email
        if hasattr(serializer, "generated_password"):
            creds["initial_password"] = serializer.generated_password
        if creds:
            emp_data["credentials"] = creds
            # Cache credentials for limited retrieval window
            ttl_minutes = getattr(settings, "ONBOARDING_CREDENTIAL_TTL_MINUTES", 30)
            cache_key = f"onboarding:cred:{employee.user_id}"
            cache.set(
                cache_key,
                {
                    "username": creds.get("username"),
                    "email": creds.get("email"),
                    "initial_password": creds.get("initial_password"),
                    # Store an aware timestamp (UTC) for auditing purposes
                    "created_at": timezone.now().isoformat(),
                },
                timeout=ttl_minutes * 60,
            )
        return Response(emp_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Retrieve cached initial credentials (time-limited)",
        description=(
            "Return cached autogenerated username, email, and initial password if it "
            "is still within the TTL. After expiration this returns 404. Only Admin "
            "or Manager roles may access this resource."
        ),
        responses={
            200: OpenApiResponse(description="Credentials still available"),
            404: OpenApiResponse(description="Not found or expired"),
        },
    )
    @action(methods=["get"], detail=True, url_path="initial-credentials")
    def initial_credentials(self, request, pk=None):  # type: ignore[override]
        employee = self.get_object()
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can retrieve initial credentials."
            raise PermissionDenied(msg)
        cache_key = f"onboarding:cred:{employee.user_id}"
        data = cache.get(cache_key)
        if not data:
            return Response(
                {"detail": "Credentials not available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Regenerate initial password (invalidate previous)",
        description=(
            "Generate a new secure password for the employee's user, update the user, "
            "cache the credentials with a fresh TTL, and return them. Use when the "
            "original credentials were lost before delivery. Only Admin or Manager "
            "may call this endpoint."
        ),
        responses={200: OpenApiResponse(description="New credentials generated")},
    )
    @action(methods=["post"], detail=True, url_path="regenerate-credentials")
    def regenerate_credentials(self, request, pk=None):  # type: ignore[override]
        employee = self.get_object()
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can regenerate credentials."
            raise PermissionDenied(msg)
        new_password = _generate_secure_password()
        user = employee.user
        user.set_password(new_password)
        user.save(update_fields=["password"])
        ttl_minutes = getattr(settings, "ONBOARDING_CREDENTIAL_TTL_MINUTES", 30)
        cache_key = f"onboarding:cred:{employee.user_id}"
        # Overwrite cache
        cache.set(
            cache_key,
            {
                "username": user.username,
                "email": user.email,
                "initial_password": new_password,
                "created_at": timezone.now().isoformat(),
                "regenerated": True,
            },
            timeout=ttl_minutes * 60,
        )
        return Response(
            {
                "username": user.username,
                "email": user.email,
                "initial_password": new_password,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Onboard an existing user as Employee",
        description=(
            "Promotes an existing non-employee User to Employee. Only Admin "
            "or Manager may call this endpoint."
        ),
        examples=[
            OpenApiExample(
                "By username (minimal)",
                value={
                    "user": "empnew",
                    "department": 1,
                    "title": "Engineer",
                    "hire_date": "2025-10-01",
                },
            ),
            OpenApiExample(
                "By id (comprehensive)",
                value={
                    "user": 42,
                    "department": 3,
                    "title": "Data Analyst",
                    "hire_date": "2025-10-01",
                    "supervisor": 5,
                    "position": 7,
                    "employment_status": "active",
                    "first_name": "Alex",
                    "last_name": "Lee",
                    "employee_email": "alex.lee@company.com",
                    "phone": "+15551234567",
                    "address": "456 Market St",
                },
            ),
            OpenApiExample(
                "With CV upload (multipart)",
                summary="Use multipart/form-data with 'cv_file' field (PDF)",
                value={"user": "jsmith", "department": 2, "cv_file": "<PDF binary>"},
            ),
        ],
        responses={
            201: OpenApiResponse(
                response=EmployeeSerializer,
                description="Employee created",
            ),
        },
    )
    @action(methods=["post"], detail=False, url_path="onboard/existing")
    def onboard_existing(self, request):
        # Only elevated can onboard
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can onboard employees."
            raise PermissionDenied(msg)
        serializer = OnboardEmployeeExistingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(
            EmployeeSerializer(employee, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Bulk onboard employees (array)",
        description=(
            "Accepts a JSON array of onboarding payloads. Each item may be for\n"
            "- a new employee (use the same shape as onboard/new), or\n"
            "- an existing user (include user as username or id, "
            "like onboard/existing).\n\n"
            "The endpoint returns a list of results with either the created employee\n"
            "payload (and optional credentials for new users) or an error object."
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                description="Array of results (success or error) ",
            )
        },
        examples=[
            OpenApiExample(
                "Mixed payload",
                value=[
                    {"first_name": "Ana", "last_name": "Diaz", "department": 1},
                    {"user": "jsmith", "department": 2, "title": "QA"},
                ],
            )
        ],
    )
    @action(methods=["post"], detail=False, url_path="onboard/bulk")
    def onboard_bulk(self, request):  # noqa: C901 - allow minor complexity here
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            msg = "Only Admin or Manager can onboard employees."
            raise PermissionDenied(msg)
        payload = request.data
        if not isinstance(payload, list):
            return Response(
                {"detail": "Expected a JSON array."}, status=status.HTTP_400_BAD_REQUEST
            )
        results = []
        for item in payload:
            if not isinstance(item, dict):
                results.append({"error": "Item must be an object."})
                continue
            try:
                if "user" in item and item["user"] not in (None, ""):
                    ser = OnboardEmployeeExistingSerializer(data=item)
                    ser.is_valid(raise_exception=True)
                    employee = ser.save()
                    results.append(
                        EmployeeSerializer(employee, context={"request": request}).data
                    )
                else:
                    ser = OnboardEmployeeNewSerializer(data=item)
                    ser.is_valid(raise_exception=True)
                    employee = ser.save()
                    emp_data = EmployeeSerializer(
                        employee, context={"request": request}
                    ).data
                    creds = {}
                    if hasattr(ser, "generated_username"):
                        creds["username"] = ser.generated_username
                    if hasattr(ser, "generated_email"):
                        creds["email"] = ser.generated_email
                    if hasattr(ser, "generated_password"):
                        creds["initial_password"] = ser.generated_password
                    if creds:
                        emp_data["credentials"] = creds
                    results.append(emp_data)
            except Exception as exc:  # noqa: BLE001 - collect per-item errors
                results.append({"error": str(exc)})
        return Response(results, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(tags=["Employee Documents"]),
    retrieve=extend_schema(tags=["Employee Documents"]),
    create=extend_schema(tags=["Employee Documents"]),
    update=extend_schema(tags=["Employee Documents"]),
    partial_update=extend_schema(tags=["Employee Documents"]),
    destroy=extend_schema(tags=["Employee Documents"]),
)
class EmployeeDocumentViewSet(viewsets.ModelViewSet[EmployeeDocument]):
    queryset = EmployeeDocument.objects.select_related("employee", "employee__user")
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        ):  # type: ignore[attr-defined]
            return qs
        return qs.filter(employee__user=u)

    def perform_create(self, serializer):
        u = self.request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        employee = serializer.validated_data.get("employee")
        if not is_elevated and getattr(employee, "user_id", None) != getattr(
            u,
            "id",
            None,
        ):
            msg = "You can only upload documents for yourself."
            raise PermissionDenied(msg)
        serializer.save()


class PositionViewSet(viewsets.ViewSet):
    """Deprecated: Position removed. Endpoint intentionally disabled."""

    permission_classes = [IsAuthenticated & IsAdminOrManagerCanWrite]
