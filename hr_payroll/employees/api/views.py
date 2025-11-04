from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.models import Contract
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument
from hr_payroll.employees.models import JobHistory
from hr_payroll.users.api.permissions import IsManagerOrAdmin

from .permissions import IsAdminOrHROrLineManagerScopedWrite
from .permissions import IsSelfEmployeeOrElevated
from .serializers import ContractSerializer
from .serializers import EmployeeCreateSerializer
from .serializers import EmployeeDocumentSerializer
from .serializers import EmployeeSerializer
from .serializers import EmployeeWriteSerializer
from .serializers import JobHistorySerializer
from .serializers import OnboardExistingSerializer
from .serializers import UserCandidateSerializer

MAX_LIMIT = 100


@extend_schema_view(
    list=extend_schema(tags=["Employees"]),
    retrieve=extend_schema(tags=["Employees"]),
    create=extend_schema(tags=["Employees"]),
    update=extend_schema(tags=["Employees"]),
    partial_update=extend_schema(tags=["Employees"]),
    destroy=extend_schema(tags=["Employees"]),
)
class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = (
        Employee.objects.select_related("user", "department", "line_manager")
        .prefetch_related(
            "documents",
            "job_history",
            "contracts",
        )
        .all()
    )
    serializer_class = EmployeeSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return EmployeeCreateSerializer
        if self.action in {"update", "partial_update"}:
            return EmployeeWriteSerializer
        if self.action == "onboard_existing":
            return OnboardExistingSerializer
        return EmployeeSerializer

    permission_classes = [IsAuthenticated]
    ordering = ("-created_at",)
    ordering_fields = ("created_at", "updated_at", "join_date", "title", "employee_id")

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.request
        # Scope: regular employees only see themselves
        u = getattr(request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            groups = getattr(u, "groups", None)
            is_hr = bool(getattr(u, "is_staff", False)) or bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            is_line_manager = bool(
                groups and groups.filter(name="Line Manager").exists()
            )
            if not (is_hr or is_line_manager):
                emp = getattr(u, "employee", None)
                # If user has no employee profile, return empty set
                if not emp:
                    return qs.none()
                qs = qs.filter(pk=getattr(emp, "pk", None))
        dept = request.query_params.get("department")
        status = request.query_params.get("status")
        q = request.query_params.get("q")
        if dept:
            # accept id or name
            if dept.isdigit():
                qs = qs.filter(department_id=int(dept))
            else:
                qs = qs.filter(department__name__icontains=dept)
        if status in {"ACTIVE", "INACTIVE"}:
            qs = qs.filter(is_active=(status == "ACTIVE"))
        if q:
            qs = qs.filter(
                Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
                | Q(title__icontains=q)
            )
        # join date range filters
        joined_after = request.query_params.get("joined_after")
        joined_before = request.query_params.get("joined_before")
        if joined_after:
            qs = qs.filter(join_date__gte=joined_after)
        if joined_before:
            qs = qs.filter(join_date__lte=joined_before)
        return qs

    def get_permissions(self):
        # Create/Delete: Admin or HR only
        if self.request and self.request.method in {"POST", "DELETE"}:
            return [IsManagerOrAdmin()]
        # Update/Patch: Admin/HR or Line Manager scoped writes
        if self.request and self.request.method in {"PUT", "PATCH"}:
            return [IsAdminOrHROrLineManagerScopedWrite()]
        return super().get_permissions()

    @extend_schema(
        tags=["Employees"],
        request=OnboardExistingSerializer,
        responses={201: EmployeeSerializer},
    )
    @action(
        detail=False,
        methods=["get", "post"],
        url_path="onboard/existing",
        permission_classes=[IsManagerOrAdmin],
    )
    def onboard_existing(self, request):
        """Create an Employee for an existing user (by id or username)."""
        # GET: return a compact schema helpful for clients
        if request.method == "GET":
            ser = self.get_serializer()
            # Build a small, stable description: field -> {required, type, help_text}
            desc = {}
            for name, field in ser.fields.items():
                desc[name] = {
                    "required": getattr(field, "required", False),
                    "type": field.__class__.__name__,
                    "help_text": getattr(field, "help_text", ""),
                }
            return Response({"fields": desc})
        # Validate payload with serializer to render proper form in browsable API
        payload_ser = self.get_serializer(data=request.data)
        payload_ser.is_valid(raise_exception=True)
        vd = payload_ser.validated_data
        # With PrimaryKeyRelatedField the serializer will return the User instance
        user = vd.get("user")

        # Prevent duplicates (serializer filters users without employees; double-check)
        if hasattr(user, "employee"):
            return Response(
                {"user": ["Employee already exists for this user."]}, status=400
            )

        # Create base Employee for this user
        emp = Employee.objects.create(user=user)

        # Map optional fields into the write serializer (no line manager selection)
        write_data = {}
        for key in ("title", "employee_id"):
            if key in vd:
                write_data[key] = vd[key]

        # Resolve department and auto-assign line manager from Department.manager
        dept = vd.get("department")
        lm = getattr(dept, "manager", None) if dept else None
        write_ser = EmployeeWriteSerializer(
            instance=emp, data=write_data, partial=True, context={"request": request}
        )
        write_ser.is_valid(raise_exception=True)
        emp = write_ser.save(department=dept, line_manager=lm)
        read = EmployeeSerializer(instance=emp, context={"request": request})
        return Response(read.data, status=201)

    def perform_create(self, serializer):
        # For normal employee creation (POST /employees), derive line_manager
        # from department.manager
        dept = serializer.validated_data.get("department")
        lm = getattr(dept, "manager", None) if dept else None
        serializer.save(line_manager=lm)

    @extend_schema(
        tags=["Employees"],
        description="List users without employee profiles for onboarding selection.",
        responses={200: UserCandidateSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="onboard/candidates",
        permission_classes=[IsManagerOrAdmin],
    )
    def onboard_candidates(self, request):
        user_model = get_user_model()
        qs = user_model.objects.filter(employee__isnull=True)
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )
        # limit results (default 20, max MAX_LIMIT)
        limit = request.query_params.get("limit")
        limit_int = 20
        if limit:
            try:
                limit_int = int(limit)
                if limit_int < 1:
                    limit_int = 1
                elif limit_int > MAX_LIMIT:
                    limit_int = MAX_LIMIT
            except ValueError:
                pass
        qs = qs.order_by("username")[:limit_int]
        ser = UserCandidateSerializer(qs, many=True, context={"request": request})
        return Response(ser.data)

    @extend_schema(
        tags=["Employees"],
        description=("List users with 'Line Manager' role for onboarding selection."),
        responses={200: UserCandidateSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="onboard/line-manager-candidates",
        permission_classes=[IsManagerOrAdmin],
    )
    def onboard_line_manager_candidates(self, request):
        user_model = get_user_model()
        qs = user_model.objects.filter(groups__name="Line Manager")
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )
        limit = request.query_params.get("limit")
        limit_int = 20
        if limit:
            try:
                limit_int = int(limit)
                if limit_int < 1:
                    limit_int = 1
                elif limit_int > MAX_LIMIT:
                    limit_int = MAX_LIMIT
            except ValueError:
                pass
        qs = qs.order_by("username")[:limit_int]
        ser = UserCandidateSerializer(qs, many=True, context={"request": request})
        return Response(ser.data)


@extend_schema_view(
    list=extend_schema(tags=["Employees • Documents"]),
    retrieve=extend_schema(tags=["Employees • Documents"]),
)
class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.select_related("employee").all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Allow create/update by Admin/HR or the employee themselves (scoped)
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsSelfEmployeeOrElevated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Scope: regular employees only see their documents
        u = getattr(self.request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            groups = getattr(u, "groups", None)
            is_hr = bool(getattr(u, "is_staff", False)) or bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            is_line_manager = bool(
                groups and groups.filter(name="Line Manager").exists()
            )
            if not (is_hr or is_line_manager):
                emp = getattr(u, "employee", None)
                if not emp:
                    return qs.none()
                qs = qs.filter(employee=emp)
        emp_id = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if emp_id:
            qs = qs.filter(employee_id=emp_id)
        return qs

    def perform_create(self, serializer):
        emp_id = self.kwargs.get("employee_id")
        if emp_id:
            serializer.save(employee_id=emp_id)
        else:
            # Default to current user's employee if not provided explicitly
            employee = getattr(self.request.user, "employee", None)
            if employee is not None:
                serializer.save(employee=employee)
            else:
                serializer.save()


@extend_schema_view(
    list=extend_schema(tags=["Employees • Job Histories"]),
    retrieve=extend_schema(tags=["Employees • Job Histories"]),
    create=extend_schema(tags=["Employees • Job Histories"]),
    update=extend_schema(tags=["Employees • Job Histories"]),
    partial_update=extend_schema(tags=["Employees • Job Histories"]),
    destroy=extend_schema(tags=["Employees • Job Histories"]),
)
class JobHistoryViewSet(viewsets.ModelViewSet):
    """CRUD for JobHistory records (employment events)."""

    queryset = JobHistory.objects.select_related("employee", "line_manager").all()
    serializer_class = JobHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Delete restricted to Admin/HR; create/update allowed to Admin/HR or
        # Line Manager (scoped)
        if self.request and self.request.method in {"DELETE"}:
            return [IsManagerOrAdmin()]
        if self.request and self.request.method in {"POST", "PUT", "PATCH"}:
            return [IsAdminOrHROrLineManagerScopedWrite()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Scope: regular employees only see their own history
        u = getattr(self.request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            groups = getattr(u, "groups", None)
            is_hr = bool(getattr(u, "is_staff", False)) or bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            is_line_manager = bool(
                groups and groups.filter(name="Line Manager").exists()
            )
            if not (is_hr or is_line_manager):
                emp = getattr(u, "employee", None)
                if not emp:
                    return qs.none()
                qs = qs.filter(employee=emp)
        employee_id = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs

    def perform_create(self, serializer):
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            # Validate employee existence to avoid FK integrity errors
            emp = Employee.objects.filter(pk=employee_id).first()
            if not emp:
                msg = "Employee not found."
                raise NotFound(msg)
            serializer.save(employee=emp)
        else:
            serializer.save()


@extend_schema_view(
    list=extend_schema(tags=["Employees • Contracts"]),
    retrieve=extend_schema(tags=["Employees • Contracts"]),
    create=extend_schema(tags=["Employees • Contracts"]),
    update=extend_schema(tags=["Employees • Contracts"]),
    partial_update=extend_schema(tags=["Employees • Contracts"]),
    destroy=extend_schema(tags=["Employees • Contracts"]),
)
class ContractViewSet(viewsets.ModelViewSet):
    """CRUD for Contracts attached to employees."""

    queryset = Contract.objects.select_related("employee").all()
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"DELETE"}:
            return [IsManagerOrAdmin()]
        if self.request and self.request.method in {"POST", "PUT", "PATCH"}:
            return [IsAdminOrHROrLineManagerScopedWrite()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Scope: regular employees only see their contracts
        u = getattr(self.request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            groups = getattr(u, "groups", None)
            is_hr = bool(getattr(u, "is_staff", False)) or bool(
                groups and groups.filter(name__in=["Admin", "Manager"]).exists()
            )
            is_line_manager = bool(
                groups and groups.filter(name="Line Manager").exists()
            )
            if not (is_hr or is_line_manager):
                emp = getattr(u, "employee", None)
                if not emp:
                    return qs.none()
                qs = qs.filter(employee=emp)
        employee_id = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs

    def perform_create(self, serializer):
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            serializer.save(employee_id=employee_id)
        else:
            serializer.save()
