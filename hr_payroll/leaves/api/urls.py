from django.urls import include
from django.urls import path
from rest_framework.routers import SimpleRouter

from hr_payroll.leaves.api.views import BalanceHistoryViewSet
from hr_payroll.leaves.api.views import EmployeeBalanceViewSet
from hr_payroll.leaves.api.views import LeavePolicyViewSet
from hr_payroll.leaves.api.views import LeaveRequestViewSet
from hr_payroll.leaves.api.views import LeaveTypeViewSet
from hr_payroll.leaves.api.views import PublicHolidayViewSet

router = SimpleRouter()
router.register("types", LeaveTypeViewSet)
router.register("policies", LeavePolicyViewSet)
router.register("public-holidays", PublicHolidayViewSet)
router.register(
    "employee-balances", EmployeeBalanceViewSet, basename="employee-balance"
)
router.register("requests", LeaveRequestViewSet, basename="leave-request")
router.register("balance-history", BalanceHistoryViewSet, basename="balance-history")

urlpatterns = [
    path("", include(router.urls)),
]
