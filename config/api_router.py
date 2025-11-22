from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import EmployeeRegistrationViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.payroll.api.views import PayrollCycleViewSet
from hr_payroll.payroll.api.views import PayrollRecordViewSet
from hr_payroll.payroll.api.views import PayrollReportViewSet
from hr_payroll.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()


router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
# Top-level canonical endpoints.
# Retain top-level 'attendances' to expose collection summary actions
# (e.g. /api/v1/attendances/my/summary/) without forcing a nested lookup.
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

urlpatterns += [
    path("leaves/", include("hr_payroll.leaves.api.urls")),
]
