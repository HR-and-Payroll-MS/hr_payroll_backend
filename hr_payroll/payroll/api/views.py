import uuid
from datetime import date
from decimal import Decimal
from decimal import InvalidOperation

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions
from rest_framework import viewsets
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
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipDocument
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem
from hr_payroll.policies import get_policy_document

from .serializers import BankDetailSerializer
from .serializers import BankMasterSerializer
from .serializers import DependentSerializer
from .serializers import EmployeeSalaryStructureSerializer
from .serializers import PayCycleSerializer
from .serializers import PayrollGeneralSettingSerializer
from .serializers import PayrollSlipSerializer
from .serializers import PayslipDocumentSerializer
from .serializers import PayslipLineItemSerializer
from .serializers import SalaryComponentSerializer
from .serializers import SalaryStructureItemSerializer


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
    salary_policy = (
        policy.get("salaryStructurePolicy", {}) if isinstance(policy, dict) else {}
    )
    base_salary = 0
    earnings = []
    deductions = []

    # Use salary structure + items when present
    structure = getattr(emp, "salary_structure", None)
    if structure:
        base_salary = float(structure.base_salary or 0)
        for item in structure.items.select_related("component"):
            comp = item.component
            if not comp:
                continue
            payload = {"label": comp.name, "amount": float(item.amount)}
            if comp.component_type == comp.Type.DEDUCTION:
                deductions.append(payload)
            else:
                earnings.append(payload)
    else:
        # fallback to policy template or sane default
        base_salary = float(
            salary_policy.get("baseSalaryTemplate", {}).get("gradeA", 0) or 0
        )

    # If no earnings were added, seed a basic breakdown like the frontend dummy
    if not earnings:
        allowance = round(base_salary * 0.2, 2)
        bonus = round(base_salary * 0.05, 2)
        earnings = [
            {"label": "Basic Salary", "amount": base_salary},
            {"label": "Allowance", "amount": allowance},
            {"label": "Bonus", "amount": bonus},
        ]

    if not deductions:
        gross_guess = sum(e["amount"] for e in earnings)
        tax = round(gross_guess * 0.1, 2)
        pension = round(gross_guess * 0.03, 2)
        deductions = [
            {"label": "Income Tax (10%)", "amount": tax},
            {"label": "Pension (3%)", "amount": pension},
        ]

    gross = sum(e["amount"] for e in earnings)
    total_deductions = sum(d["amount"] for d in deductions)
    net = gross - total_deductions

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
        "earnings": earnings,
        "deductions": deductions,
        "gross": gross,
        "totalDeductions": total_deductions,
        "net": net,
        "paymentMethod": "Bank Transfer",
        "paymentDate": timezone.now().date().isoformat(),
    }


class PayslipUploadView(APIView):
    """Accepts a generated payslip PDF and stores it under media/payslips.

    Designed to match the frontend call to `/api/payslips/generate/` which sends
    `pdf_file`, `employee_id`, `month`, `gross`, and `net` in multipart form data.
    """

    permission_classes = [permissions.IsAuthenticated]

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

    permission_classes = [permissions.IsAuthenticated]

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

    permission_classes = [permissions.IsAuthenticated]

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

    permission_classes = [permissions.IsAuthenticated]
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
