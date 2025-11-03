from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import ContractViewSet
from hr_payroll.employees.api.views import EmployeeDocumentViewSet
from hr_payroll.employees.api.views import EmployeeViewSet
from hr_payroll.employees.api.views import JobHistoryViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.payroll.api.views import CompensationViewSet
from hr_payroll.payroll.api.views import SalaryComponentViewSet
from hr_payroll.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()


# Hidden variants: keep routes available for backward compatibility but hide in schema
class _HiddenInSchemaMixin:
    # DRF: setting schema=None excludes endpoints from OpenAPI generation
    schema = None


class HiddenAttendanceViewSet(_HiddenInSchemaMixin, AttendanceViewSet):
    pass


class HiddenEmployeeDocumentViewSet(_HiddenInSchemaMixin, EmployeeDocumentViewSet):
    pass


class HiddenJobHistoryViewSet(_HiddenInSchemaMixin, JobHistoryViewSet):
    pass


class HiddenContractViewSet(_HiddenInSchemaMixin, ContractViewSet):
    pass


class HiddenCompensationViewSet(_HiddenInSchemaMixin, CompensationViewSet):
    pass


router.register("users", UserViewSet)
router.register("employees", EmployeeViewSet)
router.register("departments", DepartmentViewSet)
router.register("employee-documents", HiddenEmployeeDocumentViewSet)
router.register("job-histories", HiddenJobHistoryViewSet)
router.register("contracts", HiddenContractViewSet)
router.register("compensations", HiddenCompensationViewSet)
router.register("attendances", HiddenAttendanceViewSet)
# Nested employee-scoped routes for cohesion
# while keeping top-level routes for backward compatibility
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
    r"employees/(?P<employee_id>[^/.]+)/attendances",
    AttendanceViewSet,
    basename="employee-attendance",
)


app_name = "api"
urlpatterns = router.urls
