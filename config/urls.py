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
@extend_schema_view(post=extend_schema(tags=["JWT Authentication"]))
class JWTCreateView(TokenObtainPairView):
    pass


@extend_schema_view(post=extend_schema(tags=["JWT Authentication"]))
class JWTRefreshView(TokenRefreshView):
    pass


@extend_schema_view(post=extend_schema(tags=["JWT Authentication"]))
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
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
            *urlpatterns,
        ]
