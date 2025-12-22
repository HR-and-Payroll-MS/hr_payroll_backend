from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.attendance.api.views import AttendanceViewSet
from hr_payroll.employees.api.views import EmployeeRegistrationViewSet
from hr_payroll.leaves.api.views import LeavesPlaceholderViewSet
from hr_payroll.notifications.api.views import NotificationViewSet
from hr_payroll.org.api.views import DepartmentViewSet
from hr_payroll.org.api.views import OrganizationPoliciesView
from hr_payroll.org.api.views import OrganizationPolicySectionView
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
router.register("notifications", NotificationViewSet, basename="notifications")


app_name = "api"
# Prepend includes to ensure they take precedence over placeholders
urlpatterns = [
    path(
        "audit/",
        include(("hr_payroll.audit.api.urls", "audit"), namespace="audit"),
    ),
    path(
        "orgs/<int:org_id>/policies/",
        OrganizationPoliciesView.as_view(),
        name="org-policies",
    ),
    path(
        "orgs/<int:org_id>/policies",
        OrganizationPoliciesView.as_view(),
        name="org-policies-noslash",
    ),
    path(
        "orgs/<int:org_id>/policies/<str:section>/",
        OrganizationPolicySectionView.as_view(),
        name="org-policies-section",
    ),
    path(
        "orgs/<int:org_id>/policies/<str:section>",
        OrganizationPolicySectionView.as_view(),
        name="org-policies-section-noslash",
    ),
    path("leaves/", include("hr_payroll.leaves.api.urls")),
    path("payroll/", include("hr_payroll.payroll.api.urls")),
    path("efficiency/", include("hr_payroll.efficiency.api.urls")),
    *router.urls,
]
