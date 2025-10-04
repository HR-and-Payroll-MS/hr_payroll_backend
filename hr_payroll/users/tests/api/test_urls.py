from django.urls import resolve
from django.urls import reverse

from hr_payroll.users.models import User


def test_user_detail(user: User):
    assert (
        reverse("api_v1:user-detail", kwargs={"username": user.username})
        == f"/api/v1/users/{user.username}/"
    )
    assert resolve(f"/api/v1/users/{user.username}/").view_name == "api_v1:user-detail"


def test_user_list():
    assert reverse("api_v1:user-list") == "/api/v1/users/"
    assert resolve("/api/v1/users/").view_name == "api_v1:user-list"


def test_user_me():
    assert reverse("api_v1:user-me") == "/api/v1/users/me/"
    assert resolve("/api/v1/users/me/").view_name == "api_v1:user-me"
