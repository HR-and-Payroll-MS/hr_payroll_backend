from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import EmployeeRegistrationViewSet
from hr_payroll.leaves.api.views import LeavesPlaceholderViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.payroll.api.views import PayrollPlaceholderViewSet
from hr_payroll.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("leaves", LeavesPlaceholderViewSet, basename="leaves")
router.register("payroll", PayrollPlaceholderViewSet, basename="payroll")
router.register("departments", DepartmentViewSet)
# Top-level canonical endpoints.
# Retain top-level 'attendances' to expose collection summary actions
# (e.g. /api/v1/attendances/my/summary/) without forcing a nested lookup.
router.register("attendances", AttendanceViewSet)
# New clean employees endpoint using registration viewset
router.register("employees", EmployeeRegistrationViewSet, basename="employees")


app_name = "api"
# Prepend includes to ensure they take precedence over placeholders
urlpatterns = [
    path("leaves/", include("hr_payroll.leaves.api.urls")),
    path("payroll/", include("hr_payroll.payroll.api.urls")),
    *router.urls,
]
