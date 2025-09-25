from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models import Department, Employee, EmployeeDocument
from .permissions import IsAdminOrManagerCanWrite, IsSelfEmployeeOrElevated
from .serializers import (
    DepartmentSerializer,
    EmployeeDocumentSerializer,
    EmployeeSerializer,
    OnboardEmployeeNewSerializer,
    OnboardEmployeeExistingSerializer,
)


class DepartmentViewSet(viewsets.ModelViewSet[Department]):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated & IsAdminOrManagerCanWrite]


class EmployeeViewSet(viewsets.ModelViewSet[Employee]):
    queryset = Employee.objects.select_related("user", "department")
    serializer_class = EmployeeSerializer
    # Authenticated users can read (limited by queryset), only elevated can write
    permission_classes = [IsAdminOrManagerCanWrite]

    def get_serializer_class(self):  # noqa: D401
        if getattr(self, "action", None) == "onboard_new":
            return OnboardEmployeeNewSerializer
        if getattr(self, "action", None) == "onboard_existing":
            return OnboardEmployeeExistingSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, "is_staff", False) or (getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()):  # type: ignore[attr-defined]
            return qs
        # Regular employees: only see their own record
        return qs.filter(user=u)

    # Prefer the onboarding endpoints in docs; keep create available but hide it from schema
    @extend_schema(exclude=True)
    def create(self, request, *args, **kwargs):  # noqa: D401
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Onboard a brand-new employee (create User + Employee)",
        description=(
            "Creates a new active User (email marked verified) and the corresponding Employee. "
            "Only Admin or Manager may call this endpoint."
        ),
        responses={201: OpenApiResponse(response=EmployeeSerializer, description="Employee created")},
    )
    @action(methods=["post"], detail=False, url_path="onboard/new")
    def onboard_new(self, request):  # noqa: D401
        # Only elevated can onboard
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            raise PermissionDenied("Only Admin or Manager can onboard employees.")
        serializer = OnboardEmployeeNewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(EmployeeSerializer(employee, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Onboard an existing user as Employee",
        description=(
            "Promotes an existing non-employee User to Employee. Only Admin or Manager may call this endpoint."
        ),
        responses={201: OpenApiResponse(response=EmployeeSerializer, description="Employee created")},
    )
    @action(methods=["post"], detail=False, url_path="onboard/existing")
    def onboard_existing(self, request):  # noqa: D401
        # Only elevated can onboard
        u = request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        if not is_elevated:
            raise PermissionDenied("Only Admin or Manager can onboard employees.")
        serializer = OnboardEmployeeExistingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(EmployeeSerializer(employee, context={"request": request}).data, status=status.HTTP_201_CREATED)


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
        if getattr(u, "is_staff", False) or (getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()):  # type: ignore[attr-defined]
            return qs
        return qs.filter(employee__user=u)

    def perform_create(self, serializer):
        u = self.request.user
        is_elevated = getattr(u, "is_staff", False) or (
            getattr(u, "groups", None) and u.groups.filter(name__in=["Admin", "Manager"]).exists()
        )  # type: ignore[attr-defined]
        employee = serializer.validated_data.get("employee")
        if not is_elevated and getattr(employee, "user_id", None) != getattr(u, "id", None):
            raise PermissionDenied("You can only upload documents for yourself.")
        serializer.save()
