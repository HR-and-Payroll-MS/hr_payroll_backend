import uuid
from datetime import date
from decimal import Decimal
from decimal import InvalidOperation

from django.db.models import Count
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from hr_payroll.employees.api.permissions import IsAdminOrPayrollOnly
from hr_payroll.employees.models import Employee
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollGeneralSetting
from hr_payroll.payroll.models import PayrollRun
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipDocument
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.payroll.models import TaxCode
from hr_payroll.payroll.models import TaxCodeVersion
from hr_payroll.payroll.services import PayrollCalculator
from hr_payroll.policies import get_policy_document

from .serializers import BankDetailSerializer
from .serializers import BankMasterSerializer
from .serializers import DependentSerializer
from .serializers import EmployeeSalaryStructureSerializer
from .serializers import PayCycleSerializer
from .serializers import PayrollGeneralSettingSerializer
from .serializers import PayrollReportRowSerializer
from .serializers import PayrollRunSerializer
from .serializers import PayrollSlipSerializer
from .serializers import PayslipDocumentSerializer
from .serializers import PayslipLineItemSerializer
from .serializers import SalaryComponentSerializer
from .serializers import SalaryStructureItemSerializer
from .serializers import TaxCodeSerializer
from .serializers import TaxCodeVersionSerializer


def _employee_basic_payload(emp: Employee) -> dict:
    user = getattr(emp, "user", None)
    name = None
    if user:
        name = (
            getattr(user, "name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )
    dept = getattr(emp, "department", None)
    bank_detail = getattr(emp, "bank_detail", None)
    return {
        "id": emp.pk,
        "employee_id": emp.employee_id,
        "name": name,
        "department": getattr(dept, "name", None),
        "jobTitle": emp.title or None,
        "bankAccount": getattr(bank_detail, "account_number", None),
    }


def _payroll_preview_payload(emp: Employee, month: str | None) -> dict:
    policy = get_policy_document(org_id=1)

    # Use the centralized calculator for consistency
    calculator = PayrollCalculator(emp)
    result = calculator.calculate()

    bank_detail = getattr(emp, "bank_detail", None)
    dept = getattr(emp, "department", None)
    user = getattr(emp, "user", None)
    name = None
    if user:
        name = (
            getattr(user, "name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )

    # basic company info from policy or defaults
    general = policy.get("general", {}) if isinstance(policy, dict) else {}
    company = {
        "name": general.get("companyName") or "HR & Payroll",
        "address": general.get("address") or "",
        "phone": general.get("phone") or "",
        "email": general.get("adminContact") or "",
        "logoUrl": "",
    }

    return {
        "employee": {
            "id": emp.pk,
            "employee_id": emp.employee_id,
            "name": name,
            "department": getattr(dept, "name", None),
            "jobTitle": emp.title or None,
            "bankAccount": getattr(bank_detail, "account_number", None),
        },
        "month": month,
        "company": company,
        "earnings": result["earnings"],
        "deductions": result["deductions"],  # Includes taxes
        "gross": result["total_earnings"],
        "totalDeductions": result["total_deductions"],
        "net": result["net_pay"],
        "paymentMethod": "Bank Transfer",
        "paymentDate": timezone.now().date().isoformat(),
    }


class PayslipUploadView(APIView):
    """Accepts a generated payslip PDF and stores it under media/payslips.

    Designed to match the frontend call to `/api/payslips/generate/` which sends
    `pdf_file`, `employee_id`, `month`, `gross`, and `net` in multipart form data.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]

    @extend_schema(
        tags=["Payroll • Payslips"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "pdf_file": {"type": "string", "format": "binary"},
                    "employee_id": {"type": "string"},
                    "month": {"type": "string"},
                    "gross": {"type": "string"},
                    "net": {"type": "string"},
                },
                "required": ["pdf_file"],
            }
        },
        responses={201: {"type": "object"}},
    )
    def post(self, request):
        pdf_file = request.FILES.get("pdf_file")
        if not pdf_file:
            return Response({"detail": "pdf_file is required"}, status=400)

        employee_id = request.data.get("employee_id") or request.data.get("employee")
        if not employee_id:
            return Response({"detail": "employee_id is required"}, status=400)

        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"detail": "Employee not found"}, status=404)

        month = (request.data.get("month") or "").strip()
        gross_raw = request.data.get("gross")
        net_raw = request.data.get("net")

        def _as_decimal(value) -> Decimal:
            if value in (None, ""):
                return Decimal("0.00")
            try:
                return Decimal(str(value))
            except (InvalidOperation, TypeError):
                return Decimal("0.00")

        gross = _as_decimal(gross_raw)
        net = _as_decimal(net_raw)

        # Try to associate to a cycle that covers the month, if one exists.
        cycle = None
        try:
            year_str, month_str = month.split("-")
            cycle_date = date(int(year_str), int(month_str), 1)
            cycle = PayCycle.objects.filter(
                start_date__lte=cycle_date, end_date__gte=cycle_date
            ).first()
        except (ValueError, AttributeError):
            cycle = None

        timestamp = timezone.now().strftime("%Y%m%dT%H%M%S")
        safe_emp = (str(employee_id) or "unknown").replace("/", "-")
        filename = (
            f"payslips/{month or 'unknown'}_{safe_emp}_{timestamp}_"
            f"{uuid.uuid4().hex}.pdf"
        )

        document = PayslipDocument(
            employee=employee,
            cycle=cycle,
            month=month,
            gross=gross,
            net=net,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        # Saves the file using the model's FileField storage backend.
        document.file.save(filename, pdf_file, save=True)
        document.save()

        serializer = PayslipDocumentSerializer(document)
        return Response(serializer.data, status=201)


class PayrollEmployeeListView(APIView):
    """Return a lightweight list of employees for payroll selection.

    Matches frontend expectations for columns:
    id, name, department, jobTitle, bankAccount.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]

    @extend_schema(
        tags=["Payroll • Employees"],
        responses={200: {"type": "array", "items": {"type": "object"}}},
    )
    def get(self, request):
        qs = Employee.objects.select_related(
            "user", "department", "bank_detail"
        ).order_by("user__username")
        data = [_employee_basic_payload(emp) for emp in qs]
        return Response(data, status=200)


class PayrollPreviewView(APIView):
    """Return a payroll preview payload for a single employee and month."""

    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]

    @extend_schema(
        tags=["Payroll • Preview"],
        parameters=[
            OpenApiParameter(
                name="month",
                required=False,
                type=str,
                description="Month in YYYY-MM format; defaults to current month",
            )
        ],
        responses={200: {"type": "object"}},
    )
    def get(self, request, employee_id: int):
        try:
            emp = (
                Employee.objects.select_related(
                    "user", "department", "bank_detail", "salary_structure"
                )
                .prefetch_related("salary_structure__items__component")
                .get(pk=employee_id)
            )
        except Employee.DoesNotExist:
            return Response({"detail": "Employee not found"}, status=404)

        month = request.query_params.get("month")
        if not month:
            month = timezone.now().strftime("%Y-%m")

        payload = _payroll_preview_payload(emp, month)
        return Response(payload, status=200)


class PayrollPlaceholderViewSet(viewsets.ViewSet):
    """
    Placeholder ViewSet to show 'payroll' in API root.
    Actual endpoints are nested under /api/v1/payroll/
    """

    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    serializer_class = None  # Explicitly set to avoid drf_spectacular warning

    @extend_schema(exclude=True)
    def list(self, request):
        return Response({"message": "Payroll API Root"})


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Bank Masters"]),
    retrieve=extend_schema(tags=["Payroll • Bank Masters"]),
    create=extend_schema(tags=["Payroll • Bank Masters"]),
    update=extend_schema(tags=["Payroll • Bank Masters"]),
    partial_update=extend_schema(tags=["Payroll • Bank Masters"]),
    destroy=extend_schema(tags=["Payroll • Bank Masters"]),
)
class BankMasterViewSet(viewsets.ModelViewSet):
    queryset = BankMaster.objects.all()
    serializer_class = BankMasterSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    search_fields = ["name", "swift_code"]
    ordering_fields = ["name"]
    ordering = ["name"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Salary Components"]),
    retrieve=extend_schema(tags=["Payroll • Salary Components"]),
    create=extend_schema(tags=["Payroll • Salary Components"]),
    update=extend_schema(tags=["Payroll • Salary Components"]),
    partial_update=extend_schema(tags=["Payroll • Salary Components"]),
    destroy=extend_schema(tags=["Payroll • Salary Components"]),
)
class SalaryComponentViewSet(viewsets.ModelViewSet):
    queryset = SalaryComponent.objects.all()
    serializer_class = SalaryComponentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["component_type", "is_taxable", "is_recurring"]
    search_fields = ["name"]
    ordering_fields = ["name", "component_type"]
    ordering = ["component_type", "name"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Settings"]),
    retrieve=extend_schema(tags=["Payroll • Settings"]),
    update=extend_schema(tags=["Payroll • Settings"]),
    partial_update=extend_schema(tags=["Payroll • Settings"]),
)
class PayrollGeneralSettingViewSet(viewsets.ModelViewSet):
    queryset = PayrollGeneralSetting.objects.all()
    serializer_class = PayrollGeneralSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    http_method_names = ["get", "put", "patch", "head", "options"]  # No create/delete


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Salary Structures"]),
    retrieve=extend_schema(tags=["Payroll • Salary Structures"]),
    create=extend_schema(tags=["Payroll • Salary Structures"]),
    update=extend_schema(tags=["Payroll • Salary Structures"]),
    partial_update=extend_schema(tags=["Payroll • Salary Structures"]),
    destroy=extend_schema(tags=["Payroll • Salary Structures"]),
)
class EmployeeSalaryStructureViewSet(viewsets.ModelViewSet):
    queryset = EmployeeSalaryStructure.objects.select_related(
        "employee__user"
    ).prefetch_related("items__component")
    serializer_class = EmployeeSalaryStructureSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["employee"]
    search_fields = ["employee__user__username", "employee__user__email"]
    ordering = ["-updated_at"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Salary Structure Items"]),
    retrieve=extend_schema(tags=["Payroll • Salary Structure Items"]),
    create=extend_schema(tags=["Payroll • Salary Structure Items"]),
    update=extend_schema(tags=["Payroll • Salary Structure Items"]),
    partial_update=extend_schema(tags=["Payroll • Salary Structure Items"]),
    destroy=extend_schema(tags=["Payroll • Salary Structure Items"]),
)
class SalaryStructureItemViewSet(viewsets.ModelViewSet):
    queryset = SalaryStructureItem.objects.select_related("structure", "component")
    serializer_class = SalaryStructureItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["structure", "component"]
    ordering = ["id"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Bank Details"]),
    retrieve=extend_schema(tags=["Payroll • Bank Details"]),
    create=extend_schema(tags=["Payroll • Bank Details"]),
    update=extend_schema(tags=["Payroll • Bank Details"]),
    partial_update=extend_schema(tags=["Payroll • Bank Details"]),
    destroy=extend_schema(tags=["Payroll • Bank Details"]),
)
class BankDetailViewSet(viewsets.ModelViewSet):
    queryset = BankDetail.objects.select_related("employee__user", "bank")
    serializer_class = BankDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["employee", "bank"]
    search_fields = ["employee__user__username", "account_number"]
    ordering = ["employee"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Dependents"]),
    retrieve=extend_schema(tags=["Payroll • Dependents"]),
    create=extend_schema(tags=["Payroll • Dependents"]),
    update=extend_schema(tags=["Payroll • Dependents"]),
    partial_update=extend_schema(tags=["Payroll • Dependents"]),
    destroy=extend_schema(tags=["Payroll • Dependents"]),
)
class DependentViewSet(viewsets.ModelViewSet):
    queryset = Dependent.objects.select_related("employee__user")
    serializer_class = DependentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["employee"]
    search_fields = ["employee__user__username", "name"]
    ordering = ["employee", "name"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Pay Cycles"]),
    retrieve=extend_schema(tags=["Payroll • Pay Cycles"]),
    create=extend_schema(tags=["Payroll • Pay Cycles"]),
    update=extend_schema(tags=["Payroll • Pay Cycles"]),
    partial_update=extend_schema(tags=["Payroll • Pay Cycles"]),
    destroy=extend_schema(tags=["Payroll • Pay Cycles"]),
)
class PayCycleViewSet(viewsets.ModelViewSet):
    queryset = PayCycle.objects.select_related("manager_in_charge__user")
    serializer_class = PayCycleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["status"]
    search_fields = ["name"]
    ordering = ["-start_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(
            total_payout=Sum("slips__net_pay", filter=Q(slips__status="paid")),
            employee_count=Count("slips", filter=Q(slips__status="paid")),
        )

    @extend_schema(tags=["Payroll • Pay Cycles"], responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"], url_path="generate")
    def generate(self, request, pk=None):
        """Trigger payroll calculation for this cycle."""
        from hr_payroll.payroll.services import generate_payroll_for_cycle

        cycle = self.get_object()
        if cycle.status == PayCycle.Status.CLOSED:
            return Response({"detail": "Cannot regenerate closed payroll"}, status=400)

        try:
            stats = generate_payroll_for_cycle(cycle.id)
            cycle.status = PayCycle.Status.PROCESSING
            cycle.save()
            return Response(stats, status=200)
        except Exception as e:  # noqa: BLE001 - need to catch all for user-facing error
            import traceback

            traceback.print_exc()
            return Response({"detail": str(e)}, status=500)


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Slips"]),
    retrieve=extend_schema(tags=["Payroll • Slips"]),
    create=extend_schema(tags=["Payroll • Slips"]),
    update=extend_schema(tags=["Payroll • Slips"]),
    partial_update=extend_schema(tags=["Payroll • Slips"]),
    destroy=extend_schema(tags=["Payroll • Slips"]),
)
class PayrollSlipViewSet(viewsets.ModelViewSet):
    queryset = PayrollSlip.objects.select_related(
        "employee__user", "cycle"
    ).prefetch_related("line_items")
    serializer_class = PayrollSlipSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["employee", "cycle", "status"]
    search_fields = ["employee__user__username", "employee__user__email"]
    ordering = ["-cycle__start_date", "employee"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Slip Line Items"]),
    retrieve=extend_schema(tags=["Payroll • Slip Line Items"]),
    create=extend_schema(tags=["Payroll • Slip Line Items"]),
    update=extend_schema(tags=["Payroll • Slip Line Items"]),
    partial_update=extend_schema(tags=["Payroll • Slip Line Items"]),
    destroy=extend_schema(tags=["Payroll • Slip Line Items"]),
)
class PayslipLineItemViewSet(viewsets.ModelViewSet):
    queryset = PayslipLineItem.objects.select_related("slip", "component")
    serializer_class = PayslipLineItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["slip", "category", "component"]
    search_fields = ["label"]
    ordering = ["slip", "category"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Payslip Documents"]),
    retrieve=extend_schema(tags=["Payroll • Payslip Documents"]),
    create=extend_schema(tags=["Payroll • Payslip Documents"]),
    update=extend_schema(tags=["Payroll • Payslip Documents"]),
    partial_update=extend_schema(tags=["Payroll • Payslip Documents"]),
    destroy=extend_schema(tags=["Payroll • Payslip Documents"]),
)
class PayslipDocumentViewSet(viewsets.ModelViewSet):
    queryset = PayslipDocument.objects.select_related(
        "employee__user", "cycle", "uploaded_by"
    )
    serializer_class = PayslipDocumentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["employee", "cycle", "month"]
    search_fields = ["employee__user__username", "employee__user__email"]
    ordering = ["-uploaded_at"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Tax Codes"]),
    retrieve=extend_schema(tags=["Payroll • Tax Codes"]),
    create=extend_schema(tags=["Payroll • Tax Codes"]),
    update=extend_schema(tags=["Payroll • Tax Codes"]),
    partial_update=extend_schema(tags=["Payroll • Tax Codes"]),
    destroy=extend_schema(tags=["Payroll • Tax Codes"]),
)
class TaxCodeViewSet(viewsets.ModelViewSet):
    queryset = TaxCode.objects.all()
    serializer_class = TaxCodeSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]
    ordering = ["code"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Tax Code Versions"]),
    retrieve=extend_schema(tags=["Payroll • Tax Code Versions"]),
    create=extend_schema(tags=["Payroll • Tax Code Versions"]),
    update=extend_schema(tags=["Payroll • Tax Code Versions"]),
    partial_update=extend_schema(tags=["Payroll • Tax Code Versions"]),
    destroy=extend_schema(tags=["Payroll • Tax Code Versions"]),
)
class TaxCodeVersionViewSet(viewsets.ModelViewSet):
    queryset = TaxCodeVersion.objects.select_related("tax_code")
    serializer_class = TaxCodeVersionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["tax_code"]
    search_fields = ["tax_code__code"]
    ordering_fields = ["effective_from", "effective_to", "created_at"]
    ordering = ["-effective_from"]


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Runs"]),
    retrieve=extend_schema(tags=["Payroll • Runs"]),
    create=extend_schema(tags=["Payroll • Runs"]),
    update=extend_schema(tags=["Payroll • Runs"]),
    partial_update=extend_schema(tags=["Payroll • Runs"]),
    destroy=extend_schema(tags=["Payroll • Runs"]),
)
class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.select_related(
        "cycle", "created_by", "approved_by", "finalized_by"
    )
    serializer_class = PayrollRunSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]
    filterset_fields = ["status", "cycle"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == PayrollRun.Status.FINALIZED:
            return Response({"detail": "Finalized runs are immutable"}, status=400)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == PayrollRun.Status.FINALIZED:
            return Response({"detail": "Finalized runs cannot be deleted"}, status=400)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(tags=["Payroll • Runs"], responses={200: PayrollRunSerializer})
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        run = self.get_object()
        if not run.can_approve():
            return Response({"detail": "Run cannot be approved"}, status=400)
        run.mark_approved(request.user)
        return Response(self.get_serializer(run).data, status=200)

    @extend_schema(tags=["Payroll • Runs"], responses={200: PayrollRunSerializer})
    @action(detail=True, methods=["post"], url_path="finalize")
    def finalize(self, request, pk=None):
        run = self.get_object()
        if not run.can_finalize():
            return Response({"detail": "Run cannot be finalized"}, status=400)
        run.mark_finalized(request.user)
        return Response(self.get_serializer(run).data, status=200)


class PayrollReportView(APIView):
    """Aggregated payroll reports per cycle and employee.

    Combines data from `PayrollSlip` (authoritative when present) and
    `PayslipDocument` (fallback) to produce rows expected by the frontend.
    Filters:
      - cycle: integer ID of `PayCycle`
      - employee: integer ID of `Employee`
      - month: YYYY-MM string (applies to documents)
    """

    permission_classes = [permissions.IsAuthenticated, IsAdminOrPayrollOnly]

    @extend_schema(
        tags=["Payroll • Reports"],
        parameters=[
            OpenApiParameter(
                name="cycle",
                required=False,
                type=int,
                description="Filter by PayCycle ID",
            ),
            OpenApiParameter(
                name="employee",
                required=False,
                type=int,
                description="Filter by Employee ID",
            ),
            OpenApiParameter(
                name="month",
                required=False,
                type=str,
                description="Filter documents by YYYY-MM",
            ),
        ],
        responses={200: {"type": "array", "items": {"type": "object"}}},
    )
    def get(self, request):
        cycle_id = request.query_params.get("cycle")
        employee_id = request.query_params.get("employee")
        month = request.query_params.get("month")

        slips_qs = PayrollSlip.objects.select_related("employee__user", "cycle")
        if cycle_id:
            slips_qs = slips_qs.filter(cycle_id=cycle_id)
        if employee_id:
            slips_qs = slips_qs.filter(employee_id=employee_id)

        rows: list[dict] = []
        covered_pairs: set[tuple[int | None, int]] = set()

        for slip in slips_qs:
            emp = slip.employee
            user = getattr(emp, "user", None)
            name = (
                getattr(user, "name", None)
                or getattr(user, "username", None)
                or getattr(user, "email", None)
            )
            rows.append(
                {
                    "cycle_id": getattr(slip.cycle, "id", None),
                    "cycle_name": getattr(slip.cycle, "name", None),
                    "employee_id": emp.pk,
                    "employee_name": name,
                    "base_salary": slip.base_salary,
                    "total_earnings": slip.total_earnings,
                    "total_deductions": slip.total_deductions,
                    "gross": slip.total_earnings,
                    "net": slip.net_pay,
                    "source": "slip",
                }
            )
            covered_pairs.add((getattr(slip.cycle, "id", None), emp.pk))

        docs_qs = PayslipDocument.objects.select_related("employee__user", "cycle")
        if cycle_id:
            docs_qs = docs_qs.filter(cycle_id=cycle_id)
        if employee_id:
            docs_qs = docs_qs.filter(employee_id=employee_id)
        if month:
            docs_qs = docs_qs.filter(month=month)

        for doc in docs_qs:
            pair = (getattr(doc.cycle, "id", None), doc.employee_id)
            if pair in covered_pairs:
                continue
            user = getattr(doc.employee, "user", None)
            name = (
                getattr(user, "name", None)
                or getattr(user, "username", None)
                or getattr(user, "email", None)
            )
            rows.append(
                {
                    "cycle_id": getattr(doc.cycle, "id", None),
                    "cycle_name": getattr(doc.cycle, "name", None),
                    "employee_id": doc.employee_id,
                    "employee_name": name,
                    "base_salary": None,
                    "total_earnings": None,
                    "total_deductions": None,
                    "gross": doc.gross,
                    "net": doc.net,
                    "source": "document",
                }
            )

        serializer = PayrollReportRowSerializer(rows, many=True)
        return Response(serializer.data, status=200)
