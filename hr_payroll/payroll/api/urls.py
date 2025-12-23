from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BankDetailViewSet
from .views import BankMasterViewSet
from .views import DependentViewSet
from .views import EmployeeSalaryStructureViewSet
from .views import PayCycleViewSet
from .views import PayrollEmployeeListView
from .views import PayrollGeneralSettingViewSet
from .views import PayrollPreviewView
from .views import PayrollRunViewSet
from .views import PayrollSlipViewSet
from .views import PayslipDocumentViewSet
from .views import PayslipLineItemViewSet
from .views import PayslipUploadView
from .views import SalaryComponentViewSet
from .views import SalaryStructureItemViewSet
from .views import TaxCodeVersionViewSet
from .views import TaxCodeViewSet

router = DefaultRouter()
router.register("banks", BankMasterViewSet, basename="bank-master")
router.register("components", SalaryComponentViewSet, basename="salary-component")
router.register("settings", PayrollGeneralSettingViewSet, basename="payroll-setting")
router.register(
    "salary-structures", EmployeeSalaryStructureViewSet, basename="salary-structure"
)
router.register(
    "structure-items", SalaryStructureItemViewSet, basename="structure-item"
)
router.register("bank-details", BankDetailViewSet, basename="bank-detail")
router.register("dependents", DependentViewSet, basename="dependent")
router.register("cycles", PayCycleViewSet, basename="pay-cycle")
router.register("slips", PayrollSlipViewSet, basename="payroll-slip")
router.register("slip-items", PayslipLineItemViewSet, basename="slip-item")
router.register(
    "payslip-documents", PayslipDocumentViewSet, basename="payslip-document"
)
router.register("tax-codes", TaxCodeViewSet, basename="tax-code")
router.register("tax-code-versions", TaxCodeVersionViewSet, basename="tax-code-version")
router.register("runs", PayrollRunViewSet, basename="payroll-run")

urlpatterns = [
    # Compatibility with frontend call `/api/payslips/generate/`
    path("payslips/generate/", PayslipUploadView.as_view(), name="payslip-generate"),
    path(
        "payroll/employees/",
        PayrollEmployeeListView.as_view(),
        name="payroll-employees",
    ),
    path(
        "payroll/employees/<int:employee_id>/preview/",
        PayrollPreviewView.as_view(),
        name="payroll-preview",
    ),
    *router.urls,
]
