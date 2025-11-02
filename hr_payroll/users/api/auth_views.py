from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import timedelta

from dj_rest_auth.views import LoginView
from django.conf import settings
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView


def _set_cookie(
    response: Response,
    name: str,
    value: str,
    max_age: int | None,
) -> None:
    if not value:
        return
    cookie_kwargs = {
        "httponly": True,
        "secure": getattr(settings, "JWT_AUTH_COOKIE_SECURE", not settings.DEBUG),
        "samesite": getattr(settings, "JWT_AUTH_COOKIE_SAMESITE", "Lax"),
        "path": "/",
    }
    if max_age is not None:
        cookie_kwargs["max_age"] = max_age
    response.set_cookie(name, value, **cookie_kwargs)


def _set_jwt_cookies(
    response: Response, access: str | None, refresh: str | None
) -> None:
    access_lifetime: timedelta = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    refresh_lifetime: timedelta = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

    access_cookie = getattr(settings, "JWT_AUTH_COOKIE", "access_token")
    refresh_cookie = getattr(settings, "JWT_AUTH_REFRESH_COOKIE", "refresh_token")

    if access:
        _set_cookie(
            response, access_cookie, access, int(access_lifetime.total_seconds())
        )
    if refresh:
        _set_cookie(
            response, refresh_cookie, refresh, int(refresh_lifetime.total_seconds())
        )


class CookieOnlyLoginView(LoginView):
    """Login that sets HttpOnly JWT cookies and scrubs tokens from JSON body."""

    def post(self, request, *args, **kwargs):  # type: ignore[override]
        response: Response = super().post(request, *args, **kwargs)
        if isinstance(response.data, dict):
            access = response.data.get("access")
            refresh = response.data.get("refresh")
            if access or refresh:
                _set_jwt_cookies(response, access, refresh)
                response.data = {"detail": "login successful"}
        return response


class CookieOnlyJWTRefreshView(TokenRefreshView):
    """Refresh that sets HttpOnly JWT cookies and scrubs tokens from JSON body."""

    def post(self, request, *args, **kwargs):  # type: ignore[override]
        response: Response = super().post(request, *args, **kwargs)
        if isinstance(response.data, dict):
            access = response.data.get("access")
            refresh = response.data.get("refresh")
            if access or refresh:
                _set_jwt_cookies(response, access, refresh)
                response.data = {"detail": "refresh successful"}
        return response
