from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

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

# API URLS
urlpatterns += [
    # API base url (namespace 'api')
    path("api/", include(("config.api_router", "api"), namespace="api")),
    # API v1 alias (namespace 'api_v1')
    path("api/v1/", include(("config.api_router", "api"), namespace="api_v1")),
    # DRF auth token
    path("api/auth-token/", obtain_auth_token, name="obtain_auth_token"),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
    # v1 schema/docs
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="api-schema-v1"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema-v1"),
        name="api-docs-v1",
    ),
    # dj-rest-auth (JWT enabled via REST_USE_JWT=True)
    # Namespace these includes to prevent name collisions with allauth's routes
    # (e.g., 'account_email_verification_sent', 'account_confirm_email').
    path(
        "api/auth/",
        include(("dj_rest_auth.urls", "dj_rest_auth"), namespace="dj_rest_auth"),
    ),
    # Registration endpoints removed: only managers/admins can create users via Djoser
    # v1 dj-rest-auth aliases
    path(
        "api/v1/auth/",
        include(("dj_rest_auth.urls", "dj_rest_auth"), namespace="dj_rest_auth_v1"),
    ),
    # v1 registration endpoints removed
    # Safety net: if any browser hits these dj-rest-auth HTML routes,
    # redirect to SSR/allauth equivalents
    # Registration-related redirect helpers removed
    # v1 safety net redirects
    # v1 registration-related redirect helpers removed
    # Djoser endpoints (users + JWT)
    path("api/auth/", include("djoser.urls")),
    path("api/auth/", include("djoser.urls.jwt")),
    # v1 Djoser aliases
    path("api/v1/auth/", include("djoser.urls")),
    path("api/v1/auth/", include("djoser.urls.jwt")),
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
