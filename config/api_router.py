from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import EmployeeRegistrationViewSet
from hr_payroll.leaves.api.views import BalanceHistoryViewSet
from hr_payroll.leaves.api.views import EmployeeBalanceViewSet
from hr_payroll.leaves.api.views import LeavePolicyViewSet
from hr_payroll.leaves.api.views import LeaveRequestViewSet
from hr_payroll.leaves.api.views import LeaveTypeViewSet
from hr_payroll.leaves.api.views import PublicHolidayViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.payroll.api.views import PayrollCycleViewSet
from hr_payroll.payroll.api.views import PayrollRecordViewSet
from hr_payroll.payroll.api.views import PayrollReportViewSet
from hr_payroll.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()


router.register("users", UserViewSet)
router.register("leave-types", LeaveTypeViewSet)
router.register("leave-policies", LeavePolicyViewSet)
router.register("public-holidays", PublicHolidayViewSet)
router.register(
    "employee-balances", EmployeeBalanceViewSet, basename="employee-balance"
)
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register("balance-history", BalanceHistoryViewSet, basename="balance-history")
router.register("departments", DepartmentViewSet)
# Top-level canonical endpoints.
# Retain top-level 'attendances' to expose collection summary actions
router.register("attendances", AttendanceViewSet)

router.register(r"payroll/cycles", PayrollCycleViewSet, basename="payroll-cycle")
router.register(r"payroll/records", PayrollRecordViewSet, basename="payroll-record")
router.register(r"payroll/reports", PayrollReportViewSet, basename="payroll-report")
# New clean employees endpoint using registration viewset
router.register("employees", EmployeeRegistrationViewSet, basename="employees")
# Remove nested attendances to avoid duplication; rely on top-level with
# filters.


app_name = "api"
urlpatterns = router.urls
