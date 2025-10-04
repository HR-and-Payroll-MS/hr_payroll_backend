from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.api.permissions import IsAdminOrManagerCanWrite
from hr_payroll.employees.api.serializers import DepartmentSerializer
from hr_payroll.employees.api.serializers import EmployeeDocumentSerializer
from hr_payroll.employees.api.serializers import EmployeeSerializer
from hr_payroll.employees.api.serializers import OnboardEmployeeExistingSerializer
from hr_payroll.employees.api.serializers import OnboardEmployeeNewSerializer
from hr_payroll.employees.api.serializers import _generate_secure_password
from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument


class DepartmentViewSet(viewsets.ModelViewSet[Department]):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated & IsAdminOrManagerCanWrite]


class EmployeeViewSet(viewsets.ModelViewSet[Employee]):
    queryset = Employee.objects.select_related("user", "department")
    serializer_class = EmployeeSerializer
    # Authenticated users can read (limited by queryset), only elevated can write
    permission_classes = [IsAdminOrManagerCanWrite]

    def get_serializer_class(self):
        if getattr(self, "action", None) == "onboard_new":
            return OnboardEmployeeNewSerializer
        if getattr(self, "action", None) == "onboard_existing":
            return OnboardEmployeeExistingSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, "is_staff", False) or (
            getattr(u, "groups", None)
            and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        ):  # type: ignore[attr-defined]
            return qs
        # Regular employees: only see their own record
        return qs.filter(user=u)

    # Prefer the onboarding endpoints in docs; keep create available
    # but hide it from the schema for clarity.
    @extend_schema(exclude=True)
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Onboard a brand-new employee (create User + Employee)",
        description=(
            "Creates a new active User (email marked verified) and the "
            "corresponding Employee. Only Admin or Manager may call this "
            "endpoint."
        ),
        responses={
            201: OpenApiResponse(
                response=EmployeeSerializer,
                description="Employee created",
            ),
        },
    )
    @action(methods=["post"], detail=False, url_path="onboard/new")
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


class EmployeeDocumentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet[EmployeeDocument],
):
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
