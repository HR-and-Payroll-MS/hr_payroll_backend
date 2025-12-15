from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.response import Response

from hr_payroll.employees.api.permissions import IsAdminOrPayrollOnly
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import BankMaster
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import EmployeeSalaryStructure
from hr_payroll.payroll.models import PayCycle
from hr_payroll.payroll.models import PayrollGeneralSetting
from hr_payroll.payroll.models import PayrollSlip
from hr_payroll.payroll.models import PayslipLineItem
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.models import SalaryStructureItem

from .serializers import BankDetailSerializer
from .serializers import BankMasterSerializer
from .serializers import DependentSerializer
from .serializers import EmployeeSalaryStructureSerializer
from .serializers import PayCycleSerializer
from .serializers import PayrollGeneralSettingSerializer
from .serializers import PayrollSlipSerializer
from .serializers import PayslipLineItemSerializer
from .serializers import SalaryComponentSerializer
from .serializers import SalaryStructureItemSerializer


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
