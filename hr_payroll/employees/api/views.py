from django.db import models
from django.db import transaction
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.models import Employee

from .permissions import IsAdminOrManagerCanWrite
from .permissions import IsSelfEmployeeOrElevated
from .permissions import _user_in_groups
from .serializers import EmployeeReadSerializer
from .serializers import EmployeeRegistrationSerializer
from .serializers import EmployeeUpdateSerializer


@extend_schema_view(
    list=extend_schema(tags=["Employees"]),
    retrieve=extend_schema(tags=["Employees"]),
)
class EmployeeRegistrationViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all().select_related("user", "department")
    serializer_class = EmployeeReadSerializer
    permission_classes = [IsAuthenticated, IsSelfEmployeeOrElevated]

    def get_queryset(self):
        """Scope employees by role.

        - Admin/staff: all employees
                - Manager group: employees in departments managed by my
                    employee record or my direct reports
        - Line Manager group: my department employees or my direct reports
        - Employee (default): only myself
        """
        qs = super().get_queryset()
        u = getattr(self.request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return qs.none()
        # Admin/staff gets all
        if getattr(u, "is_staff", False) or _user_in_groups(u, ["Admin"]):
            return qs
        # Resolve requester employee
        req_emp = getattr(u, "employee", None)
        if req_emp is None:
            return qs.none()
        is_manager = _user_in_groups(u, ["Manager"])
        is_line_manager = _user_in_groups(u, ["Line Manager"])
        if is_manager:
            # Employees in departments I manage + my direct reports
            dept_ids = list(req_emp.managed_departments.values_list("id", flat=True))
            return qs.filter(
                models.Q(department_id__in=dept_ids)
                | models.Q(line_manager_id=req_emp.id)
                | models.Q(user_id=u.id)
            )
        if is_line_manager:
            # My department employees + my direct reports
            dept_id = getattr(req_emp, "department_id", None)
            return qs.filter(
                models.Q(department_id=dept_id)
                | models.Q(line_manager_id=req_emp.id)
                | models.Q(user_id=u.id)
            )
        # Default employee: only self
        return qs.filter(user_id=u.id)

    def get_serializer_class(self):
        # Registration and create use the registration serializer
        if getattr(self, "action", None) in {"register", "create"}:
            return EmployeeRegistrationSerializer
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return EmployeeUpdateSerializer
        return EmployeeReadSerializer

    def get_permissions(self):
        # Restrict create/destroy to Admin/Manager; others use default perms
        if getattr(self, "action", None) in {"create", "destroy"}:
            return [IsAuthenticated(), IsAdminOrManagerCanWrite()]
        return [perm() for perm in self.permission_classes]

    @extend_schema(
        tags=["Employees"],
        request=EmployeeRegistrationSerializer,
        responses={201: EmployeeReadSerializer},
        examples=[
            OpenApiExample(
                name="Registration",
                value={
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "gender": "Female",
                    "date_of_birth": "1990-05-10",
                    "phone": "+251911111111",
                    "nationality": "Ethiopian",
                    "health_care": "Plan A",
                    "marital_status": "Single",
                    "personal_tax_id": "TIN12345",
                    "social_insurance": "PEN12345",
                    "department_id": 1,
                    "office": "HQ",
                    "time_zone": "Africa/Addis_Ababa",
                    "title": "Engineer",
                    "join_date": "2025-11-01",
                    "job_effective_date": "2025-11-01",
                    "job_position_type": "IC",
                    "job_employment_type": "fulltime",
                    "contract_number": "C-100",
                    "contract_name": "Fulltime",
                    "contract_type": "permanent",
                    "contract_start_date": "2025-11-01",
                    "components": [
                        {"kind": "recurring", "amount": "500.00", "label": "Transport"}
                    ],
                    "dependents": [
                        {
                            "name": "Sam",
                            "relationship": "Child",
                            "date_of_birth": "2015-06-15",
                        }
                    ],
                    "bank_name": "ACME",
                    "account_name": "Payroll",
                    "account_number": "123456",
                },
                request_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="register",
        permission_classes=[IsAuthenticated, IsAdminOrManagerCanWrite],
    )
    def register(self, request):
        ser = EmployeeRegistrationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})
        data = read.data
        creds = getattr(ser, "created_credentials", None)
        if creds:
            data = dict(data)
            data["credentials"] = creds
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeRegistrationSerializer,
        responses={201: EmployeeReadSerializer},
    )
    def create(self, request, *args, **kwargs):
        ser = EmployeeRegistrationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})
        data = read.data
        creds = getattr(ser, "created_credentials", None)
        if creds:
            data = dict(data)
            data["credentials"] = creds
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeUpdateSerializer,
        responses={200: EmployeeReadSerializer},
    )
    def update(self, request, *args, **kwargs):
        partial = False
        inst = self.get_object()
        ser = EmployeeUpdateSerializer(inst, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})
        return Response(read.data)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeUpdateSerializer,
        responses={200: EmployeeReadSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        partial = True
        inst = self.get_object()
        ser = EmployeeUpdateSerializer(inst, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})
        return Response(read.data)

    @extend_schema(tags=["Employees"], responses={204: None})
    def destroy(self, request, *args, **kwargs):
        inst = self.get_object()
        with transaction.atomic():
            inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
