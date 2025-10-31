import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_model():
    return get_user_model()


@pytest.fixture
def manager(user_model):
    mgr = user_model.objects.create_user(
        username="mgrrole",
        email="mgrrole@example.com",
        password="MgrPass!123",  # noqa: S106
    )
    g, _ = Group.objects.get_or_create(name="Manager")
    mgr.groups.add(g)
    return mgr


@pytest.fixture
def employee(user_model):
    return user_model.objects.create_user(
        username="regular",
        email="regular@example.com",
        password="RegPass!123",  # noqa: S106
    )


def test_manager_lists_all_users(manager, employee, user_model):
    """Manager can list all users via internal /api/v1/users/ endpoint.

    We deliberately use the project UserViewSet route (not Djoser's /auth/users/) to
    validate custom queryset logic that exposes all users to elevated roles.
    """
    # Add a second normal user
    user_model.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="OtherPass!123",  # noqa: S106
    )
    client = APIClient()
    client.force_authenticate(user=manager)
    r = client.get("/api/v1/users/")
    assert r.status_code == status.HTTP_200_OK, r.data
    # Manager should see all three created users
    usernames = {u["username"] for u in r.data}
    assert {"mgrrole", "regular", "otheruser"}.issubset(usernames)


@pytest.mark.skipif(
    not getattr(settings, "DJOSER_ENABLED", False),
    reason="Djoser endpoints disabled in settings",
)
def test_regular_user_cannot_reset_username(employee):
    client = APIClient()
    client.force_authenticate(user=employee)
    r = client.post(
        "/api/v1/auth/users/reset_username/",
        {"email": employee.email},
        format="json",
    )
    # Should be forbidden (permission restricted to Manager/Admin)
    assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
