"""Views for Employees API."""

import contextlib
import logging
import mimetypes

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.audit.utils import log_action
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument

from .filters import EmployeeFilter
from .permissions import ROLE_ADMIN
from .permissions import ROLE_LINE_MANAGER
from .permissions import ROLE_MANAGER
from .permissions import ROLE_PAYROLL
from .permissions import IsAdminOrManagerCanWrite
from .permissions import IsSelfEmployeeOrElevated
from .permissions import _user_in_groups
from .serializers import EmployeeDocumentSerializer
from .serializers import EmployeeNestedUpdateSerializer
from .serializers import EmployeeReadSerializer
from .serializers import EmployeeRegistrationSerializer


def _log_file_upload(request_type, request):
    """Log file upload details for debugging."""
    logger.info("%s Request Data Keys: %s", request_type, list(request.data.keys()))
    logger.info("%s Request FILES Keys: %s", request_type, list(request.FILES.keys()))

    # Check for document (handling both keys)
    if "document_file" in request.FILES:
        doc_file = request.FILES["document_file"]
        logger.info(
            "Document File received: %s, size: %s", doc_file.name, doc_file.size
        )
    elif "documents" in request.FILES:
        doc_file = request.FILES["documents"]
        logger.info(
            "Document File received (as 'documents'): %s, size: %s",
            doc_file.name,
            doc_file.size,
        )
    else:
        logger.warning("No 'document_file' or 'documents' found in request.FILES")

    # Check for photo
    if "photo" in request.FILES:
        photo_file = request.FILES["photo"]
        logger.info("Photo received: %s, size: %s", photo_file.name, photo_file.size)
    else:
        logger.warning("No 'photo' found in request.FILES")


logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(tags=["Employees"]),
    retrieve=extend_schema(tags=["Employees"]),
)
class EmployeeRegistrationViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all().select_related("user", "department")
    serializer_class = EmployeeReadSerializer
    permission_classes = [IsAuthenticated, IsSelfEmployeeOrElevated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = [
        "user__first_name",
        "user__last_name",
        "user__email",
        "user__username",
    ]
    filterset_class = EmployeeFilter

    def get_queryset(self):
        """Scope employees by role.

        - Admin/Payroll/staff: all employees
        - Manager group: employees in departments I manage or my direct reports
        - Line Manager group: my department employees or my direct reports
        - Employee (default): only myself
        """
        qs = super().get_queryset()
        u = getattr(self.request, "user", None)
        if not (u and getattr(u, "is_authenticated", False)):
            return qs.none()
        # Admin/Payroll/staff get all
        if getattr(u, "is_staff", False) or _user_in_groups(
            u, [ROLE_ADMIN, ROLE_PAYROLL]
        ):
            return qs
        # Resolve requester employee
        req_emp = getattr(u, "employee", None)
        if req_emp is None:
            return qs.none()
        is_manager = _user_in_groups(u, [ROLE_MANAGER])
        is_line_manager = _user_in_groups(u, [ROLE_LINE_MANAGER])
        if is_manager:
            # Employees in departments I manage + my direct reports
            dept_ids = list(req_emp.managed_departments.values_list("id", flat=True))
            return qs.filter(
                Q(department_id__in=dept_ids)
                | Q(line_manager_id=req_emp.id)
                | Q(user_id=u.id)
            )
        if is_line_manager:
            # My department employees + my direct reports
            dept_id = getattr(req_emp, "department_id", None)
            return qs.filter(
                Q(department_id=dept_id)
                | Q(line_manager_id=req_emp.id)
                | Q(user_id=u.id)
            )
        # Default employee: only self
        return qs.filter(user_id=u.id)

    def get_serializer_class(self):
        # Registration and create use the registration serializer
        if getattr(self, "action", None) in {"register", "create"}:
            return EmployeeRegistrationSerializer
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return EmployeeNestedUpdateSerializer
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
                    "document_name": "ID Card",
                    "document_file": "<binary>",
                },
                request_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="register",
        permission_classes=[AllowAny],
    )
    def register(self, request):
        # Authenticated non-elevated users (regular employees) cannot register
        u = getattr(request, "user", None)
        if u and getattr(u, "is_authenticated", False):
            if not (
                getattr(u, "is_staff", False)
                or _user_in_groups(u, [ROLE_ADMIN, ROLE_MANAGER])
            ):
                return Response(
                    {"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN
                )
        _log_file_upload("Register", request)

        ser = EmployeeRegistrationSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()

        with contextlib.suppress(Exception):
            created_user = getattr(emp, "user", None)
            display = (
                (created_user.get_full_name() or "").strip()
                if created_user and hasattr(created_user, "get_full_name")
                else ""
            )
            if not display and created_user:
                display = getattr(created_user, "username", "")
            message = (
                f"Employee registered: {display}" if display else "Employee registered"
            )
            log_action(
                "employee_registered",
                actor=request.user,
                message=message,
                model_name="Employee",
                record_id=getattr(emp, "pk", None),
                ip_address=request.META.get("REMOTE_ADDR", "") or "",
            )
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
        _log_file_upload("Create", request)

        ser = EmployeeRegistrationSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            emp = ser.save()

        with contextlib.suppress(Exception):
            created_user = getattr(emp, "user", None)
            display = (
                (created_user.get_full_name() or "").strip()
                if created_user and hasattr(created_user, "get_full_name")
                else ""
            )
            if not display and created_user:
                display = getattr(created_user, "username", "")
            message = f"Employee created: {display}" if display else "Employee created"
            log_action(
                "employee_created",
                actor=request.user,
                message=message,
                model_name="Employee",
                record_id=getattr(emp, "pk", None),
                ip_address=request.META.get("REMOTE_ADDR", "") or "",
            )
        read = EmployeeReadSerializer(emp, context={"request": request})
        data = read.data
        creds = getattr(ser, "created_credentials", None)
        if creds:
            data = dict(data)
            data["credentials"] = creds
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeNestedUpdateSerializer,
        responses={200: EmployeeReadSerializer},
    )
    def update(self, request, *args, **kwargs):
        logger.info("=" * 80)
        logger.info("UPDATE (PUT) request for employee %s", kwargs.get("pk", "unknown"))
        logger.info("Request data keys: %s", list(request.data.keys()))
        logger.info("Full request data: %s", request.data)
        logger.info("=" * 80)

        instance = self.get_object()
        ser = EmployeeNestedUpdateSerializer(
            instance, data=request.data, partial=False, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})

        logger.info("UPDATE completed successfully for employee %s", emp.id)
        return Response(read.data)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeNestedUpdateSerializer,
        responses={200: EmployeeReadSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        logger.info("=" * 80)
        logger.info(
            "PARTIAL_UPDATE (PATCH) request for employee %s",
            kwargs.get("pk", "unknown"),
        )
        logger.info("Request data keys: %s", list(request.data.keys()))
        logger.info("Full request data: %s", request.data)
        logger.info("=" * 80)

        instance = self.get_object()
        ser = EmployeeNestedUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        emp = ser.save()
        read = EmployeeReadSerializer(emp, context={"request": request})

        logger.info("PARTIAL_UPDATE completed successfully for employee %s", emp.id)
        return Response(read.data)

    @extend_schema(tags=["Employees"], responses={204: None})
    def destroy(self, request, *args, **kwargs):
        inst = self.get_object()
        with transaction.atomic():
            inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path=r"serve-document/(?P<doc_id>\d+)")
    def serve_document(self, request, doc_id=None):
        """Serve document content globally (no employee ID needed in URL)."""
        doc = get_object_or_404(EmployeeDocument, pk=doc_id)

        # Check permissions (proxies to employee check)
        self.check_object_permissions(request, doc)

        if not doc.file:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Detect content type from file extension
        content_type, _ = mimetypes.guess_type(doc.file.name)
        if not content_type:
            content_type = "application/octet-stream"

        # Open the file and create response
        file_handle = doc.file.open("rb")
        response = HttpResponse(file_handle.read(), content_type=content_type)

        # Set Content-Disposition to inline for viewing in browser
        response["Content-Disposition"] = f'inline; filename="{doc.name}"'

        # Remove X-Frame-Options to allow iframe embedding
        response.xframe_options_exempt = True

        file_handle.close()
        return response

    @extend_schema(
        tags=["Employees"],
        request=EmployeeDocumentSerializer,
        responses={201: EmployeeDocumentSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="upload-document",
        parser_classes=[MultiPartParser],
    )
    def upload_document(self, request, pk=None):
        """Upload a new document for an employee."""
        employee = self.get_object()
        # Check write permissions for the employee
        self.check_object_permissions(request, employee)

        # IMPORTANT: avoid request.data.copy() here.
        # With multipart uploads (especially when Django spills to
        # TemporaryUploadedFile),
        # QueryDict.copy() deepcopies its contents and can crash with:
        # "cannot pickle 'BufferedRandom' instances".

        # Frontend/backward-compatible aliases:
        # - file: file | documents | document_file
        # - name: name | document_name
        file_obj = (
            request.FILES.get("file")
            or request.FILES.get("documents")
            or request.FILES.get("document_file")
        )
        name = (
            request.data.get("name") or request.data.get("document_name") or ""
        ).strip()

        if not file_obj:
            return Response(
                {
                    "detail": "Missing uploaded file.",
                    "code": "MISSING_FILE",
                    "accepted_fields": {
                        "file": ["file", "documents", "document_file"],
                        "name": ["name", "document_name"],
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not name:
            name = getattr(file_obj, "name", "Document") or "Document"

        ser = EmployeeDocumentSerializer(data={"name": name, "file": file_obj})
        ser.is_valid(raise_exception=True)
        ser.save(employee=employee)

        return Response(ser.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Employees"],
        request=EmployeeDocumentSerializer,
        responses={200: EmployeeDocumentSerializer},
    )
    @action(
        detail=False,
        methods=["put", "patch"],
        url_path=r"update-document/(?P<doc_id>\d+)",
        parser_classes=[MultiPartParser],
    )
    def update_document(self, request, doc_id=None):
        """Update an existing document (name or file)."""
        doc = get_object_or_404(EmployeeDocument, pk=doc_id)
        # Check permissions on the document
        self.check_object_permissions(request, doc)

        partial = request.method == "PATCH"

        # Accept alias keys and avoid copying multipart QueryDict.
        file_obj = (
            request.FILES.get("file")
            or request.FILES.get("documents")
            or request.FILES.get("document_file")
        )
        name = request.data.get("name") or request.data.get("document_name")

        payload = {}
        if name is not None:
            payload["name"] = str(name)
        if file_obj is not None:
            payload["file"] = file_obj

        ser = EmployeeDocumentSerializer(doc, data=payload, partial=partial)
        ser.is_valid(raise_exception=True)
        ser.save()

        return Response(ser.data)

    @extend_schema(
        tags=["Employees"],
        responses={204: None},
    )
    @action(
        detail=False, methods=["delete"], url_path=r"delete-document/(?P<doc_id>\d+)"
    )
    def delete_document(self, request, doc_id=None):
        """Delete a document."""

        doc = get_object_or_404(EmployeeDocument, pk=doc_id)
        # Check permissions on the document
        self.check_object_permissions(request, doc)

        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
