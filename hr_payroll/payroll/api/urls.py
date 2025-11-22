from rest_framework.routers import DefaultRouter

from .views import BankDetailViewSet
from .views import BankMasterViewSet
from .views import DependentViewSet
from .views import EmployeeSalaryStructureViewSet
from .views import PayCycleViewSet
from .views import PayrollGeneralSettingViewSet
from .views import PayrollSlipViewSet
from .views import PayslipLineItemViewSet
from .views import SalaryComponentViewSet
from .views import SalaryStructureItemViewSet

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

urlpatterns = router.urls
