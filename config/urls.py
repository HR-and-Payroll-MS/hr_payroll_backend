from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenVerifyView

from hr_payroll.attendance.api.views import EmployeeAttendanceViewSet
from hr_payroll.org.api.views import OrganizationPoliciesView
from hr_payroll.org.api.views import OrganizationPolicySectionView
from hr_payroll.payroll.api.views import PayslipUploadView
from hr_payroll.users.api.auth_views import CookieOnlyJWTRefreshView

from .health import health as health_view

urlpatterns = [
    path("", TemplateView.as_view(template_name="pages/home.html"), name="home"),
    path(
        "about/",
        TemplateView.as_view(template_name="pages/about.html"),
        name="about",
    ),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("hr_payroll.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    # Your stuff: custom urls includes go here
    path("health/", health_view, name="health"),
    # ...
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
if settings.DEBUG:
    # Static file serving when using Gunicorn + Uvicorn for local web socket development
    urlpatterns += staticfiles_urlpatterns()

# API URLS (only version v1 retained)
urlpatterns += [
    # Compatibility endpoint for frontend payslip uploads
    path(
        "api/payslips/generate/",
        PayslipUploadView.as_view(),
        name="payslip-generate-root",
    ),
    # Frontend compatibility: some clients call these without an /api prefix.
    # Keep these limited to organization policy endpoints.
    path(
        "orgs/<int:org_id>/policies/",
        OrganizationPoliciesView.as_view(),
        name="org-policies-root",
    ),
    path(
        "orgs/<int:org_id>/policies",
        OrganizationPoliciesView.as_view(),
        name="org-policies-root-noslash",
    ),
    path(
        "orgs/<int:org_id>/policies/<str:section>/",
        OrganizationPolicySectionView.as_view(),
        name="org-policies-root-section",
    ),
    path(
        "orgs/<int:org_id>/policies/<str:section>",
        OrganizationPolicySectionView.as_view(),
        name="org-policies-root-section-noslash",
    ),
    # Compatibility prefix for older frontend code that calls `/api/...`.
    # Prefer `/api/v1/...` long-term.
    path("api/", include(("config.api_router", "api"), namespace="api")),
    # API v1 (namespace 'api_v1')
    path("api/v1/", include(("config.api_router", "api"), namespace="api_v1")),
    # v1 schema/docs
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="api-schema-v1"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema-v1"),
        name="api-docs-v1",
    ),
    # v1 auth (dj-rest-auth) - curated to exclude token-based endpoints
    path(
        "api/v1/auth/",
        include(
            ("hr_payroll.users.api.auth_urls", "dj_rest_auth"),
            namespace="dj_rest_auth_v1",
        ),
    ),
    # v1 Djoser (users) behind feature flag
    # Enable via DJOSER_ENABLED=True in settings/env
    *(
        [path("api/v1/auth/", include("djoser.urls"))]
        if getattr(settings, "DJOSER_ENABLED", False)
        else []
    ),
    # v1 JWT endpoints (explicit to control schema tags)
]


# Annotated JWT views for proper schema tag grouping
@extend_schema_view(post=extend_schema(tags=["Authentication"]))
class JWTCreateView(TokenObtainPairView):
    pass


@extend_schema_view(post=extend_schema(tags=["Authentication"]))
class JWTRefreshView(TokenRefreshView):
    pass


@extend_schema_view(post=extend_schema(tags=["Authentication"]))
class JWTVerifyView(TokenVerifyView):
    pass


urlpatterns += [
    # JWT endpoints (login handled in curated auth urls above)
    path("api/v1/auth/jwt/create/", JWTCreateView.as_view(), name="jwt-create"),
    path(
        "api/v1/auth/jwt/refresh/",
        CookieOnlyJWTRefreshView.as_view(),
        name="jwt-refresh",
    ),
    path("api/v1/auth/jwt/verify/", JWTVerifyView.as_view(), name="jwt-verify"),
    # Body-based JWT endpoints for SPAs / djoser-style usage (keep prefix to avoid
    # colliding with cookie-only flows). These accept/return tokens in JSON
    # body and are suitable when the frontend manages tokens itself.
    path(
        "api/v1/auth/djoser/jwt/create/",
        TokenObtainPairView.as_view(),
        name="djoser-jwt-create",
    ),
    path(
        "api/v1/auth/djoser/jwt/refresh/",
        TokenRefreshView.as_view(),
        name="djoser-jwt-refresh",
    ),
    path(
        "api/v1/auth/djoser/jwt/verify/",
        TokenVerifyView.as_view(),
        name="djoser-jwt-verify",
    ),
]

# Nested Employee Attendance endpoints (manual wiring)
employee_attendance_list = EmployeeAttendanceViewSet.as_view({"get": "list"})
employee_attendance_detail = EmployeeAttendanceViewSet.as_view({"get": "retrieve"})
employee_attendance_clock_in = EmployeeAttendanceViewSet.as_view({"post": "clock_in"})
employee_attendance_clock_out = EmployeeAttendanceViewSet.as_view({"post": "clock_out"})
employee_attendance_clock_out_today = EmployeeAttendanceViewSet.as_view(
    {"post": "clock_out_today"}
)
employee_attendance_fingerprint_scan = EmployeeAttendanceViewSet.as_view(
    {"post": "fingerprint_scan"}
)
employee_attendance_network_status = EmployeeAttendanceViewSet.as_view(
    {"get": "network_status"}
)
employee_attendance_manual_entry = EmployeeAttendanceViewSet.as_view(
    {"post": "manual_entry"}
)
employee_attendance_actions = EmployeeAttendanceViewSet.as_view({"get": "actions"})
employee_attendance_today = EmployeeAttendanceViewSet.as_view({"get": "today"})
employee_attendance_check = EmployeeAttendanceViewSet.as_view({"post": "check"})

urlpatterns += [
    path(
        "api/v1/employees/<int:employee_id>/attendances/",
        employee_attendance_list,
        name="employee-attendance-list",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/clock-in/",
        employee_attendance_clock_in,
        name="employee-attendance-clock-in",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/clock-out/",
        employee_attendance_clock_out_today,
        name="employee-attendance-clock-out-today",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/fingerprint/scan/",
        employee_attendance_fingerprint_scan,
        name="employee-attendance-fingerprint-scan",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/network-status/",
        employee_attendance_network_status,
        name="employee-attendance-network-status",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/manual-entry/",
        employee_attendance_manual_entry,
        name="employee-attendance-manual-entry",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/actions/",
        employee_attendance_actions,
        name="employee-attendance-actions",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/today/",
        employee_attendance_today,
        name="employee-attendance-today",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/check/",
        employee_attendance_check,
        name="employee-attendance-check",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/<int:pk>/",
        employee_attendance_detail,
        name="employee-attendance-detail",
    ),
    path(
        "api/v1/employees/<int:employee_id>/attendances/<int:pk>/clock-out/",
        employee_attendance_clock_out,
        name="employee-attendance-clock-out",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        try:
            import debug_toolbar  # type: ignore[import-not-found]
        except ImportError:
            debug_toolbar = None  # type: ignore[assignment]
        if debug_toolbar is not None:  # type: ignore[truthy-bool]
            urlpatterns = [
                path("__debug__/", include(debug_toolbar.urls)),
                *urlpatterns,
            ]
