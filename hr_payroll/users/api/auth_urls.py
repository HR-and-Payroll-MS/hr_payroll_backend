from dj_rest_auth.views import LogoutView
from dj_rest_auth.views import PasswordChangeView
from dj_rest_auth.views import PasswordResetConfirmView
from dj_rest_auth.views import PasswordResetView
from dj_rest_auth.views import UserDetailsView
from django.urls import path

from .auth_views import CookieOnlyLoginView

# Curated auth URLs excluding token-based endpoints.
# Login is overridden to set HttpOnly JWT cookies and omit tokens from the JSON body.
urlpatterns = [
    path("login/", CookieOnlyLoginView.as_view(), name="dj-rest-auth_login"),
    path("logout/", LogoutView.as_view(), name="dj-rest-auth_logout"),
    path("password/reset/", PasswordResetView.as_view(), name="rest_password_reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="rest_password_reset_confirm",
    ),
    path("password/change/", PasswordChangeView.as_view(), name="rest_password_change"),
    path("user/", UserDetailsView.as_view(), name="rest_user_details"),
]
