from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import ContractViewSet
from hr_payroll.employees.api.views import EmployeeDocumentViewSet
from hr_payroll.employees.api.views import EmployeeViewSet
from hr_payroll.employees.api.views import JobHistoryViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.payroll.api.views import BankDetailViewSet
from hr_payroll.payroll.api.views import CompensationViewSet
from hr_payroll.payroll.api.views import DependentViewSet
from hr_payroll.payroll.api.views import PayrollCycleViewSet
from hr_payroll.payroll.api.views import PayrollRecordViewSet
from hr_payroll.payroll.api.views import PayrollReportViewSet
from hr_payroll.payroll.api.views import SalaryComponentViewSet
from hr_payroll.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()


router.register("users", UserViewSet)
router.register("employees", EmployeeViewSet)
router.register("departments", DepartmentViewSet)
# Keep only canonical top-level endpoints.
# Remove redundant top-level CRUD for nested resources.
# Retain top-level 'attendances' to expose collection actions
# (my/summary, team/summary).
router.register("attendances", AttendanceViewSet)
# Nested employee-scoped routes for cohesion while keeping
# top-level routes for backward compatibility.
router.register(
    r"employees/(?P<employee_id>[^/.]+)/job-histories",
    JobHistoryViewSet,
    basename="employee-jobhistory",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/contracts",
    ContractViewSet,
    basename="employee-contract",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/compensations",
    CompensationViewSet,
    basename="employee-compensation",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/compensations/"
    r"(?P<compensation_id>[^/.]+)/salary-components",
    SalaryComponentViewSet,
    basename="employee-compensation-salarycomponent",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/documents",
    EmployeeDocumentViewSet,
    basename="employee-document",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/bank-details",
    BankDetailViewSet,
    basename="employee-bankdetail",
)
router.register(
    r"employees/(?P<employee_id>[^/.]+)/dependents",
    DependentViewSet,
    basename="employee-dependent",
)
router.register(r"payroll/cycles", PayrollCycleViewSet, basename="payroll-cycle")
router.register(r"payroll/records", PayrollRecordViewSet, basename="payroll-record")
router.register(r"payroll/reports", PayrollReportViewSet, basename="payroll-report")
# Remove nested attendances to avoid duplication; rely on top-level with
# filters.


app_name = "api"
urlpatterns = router.urls
