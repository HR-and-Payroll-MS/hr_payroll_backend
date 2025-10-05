import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="immut001",
        email="immut001@example.com",
        password="Pass!12345",  # noqa: S106
        first_name="Old",
        last_name="Name",
    )


def test_can_update_first_last_name_only(user):
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.patch(
        f"/api/v1/users/{user.username}/",
        {"first_name": "New", "last_name": "Value"},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK, r.data
    user.refresh_from_db()
    assert user.first_name == "New"
    assert user.last_name == "Value"
    # username & email unchanged
    assert user.username == "immut001"
    assert user.email == "immut001@example.com"


def test_reject_username_email_changes(user):
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.patch(
        f"/api/v1/users/{user.username}/",
        {"username": "hacked", "email": "hack@example.com"},
        format="json",
    )
    # Both fields should trigger validation error; 400 with field errors
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in r.data
    assert "email" in r.data
    user.refresh_from_db()
    assert user.username == "immut001"
    assert user.email == "immut001@example.com"
