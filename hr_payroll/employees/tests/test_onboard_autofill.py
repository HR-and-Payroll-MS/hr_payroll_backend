from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

EXPECTED_COLLISION_COUNT = 2

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def manager_user(django_user_model):
    user = django_user_model.objects.create_user(
        username="manager",
        email="manager@example.com",
        password="manager-pass-123",  # noqa: S106 test fixture password
        first_name="Man",
        last_name="Ager",
    )
    user.is_staff = True  # treat as elevated
    user.save()
    return user


@pytest.fixture
def auth_client(api_client, manager_user):
    api_client.force_authenticate(user=manager_user)
    return api_client


def _post_onboard(client, payload):
    return client.post("/api/v1/employees/onboard/new/", payload, format="json")


def test_autofill_username_email_basic(auth_client):
    resp = _post_onboard(
        auth_client,
        {
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert resp.status_code == HTTPStatus.CREATED, resp.content
    data = resp.json()
    # Response 'user' is the username slug per EmployeeSerializer
    user_model = get_user_model()
    u = user_model.objects.get(username=data["user"])
    # Pattern j + truncated last + sequence, e.g. jdoe001
    assert u.username.startswith("jdoe")
    assert u.email == f"{u.username}@hr_payroll.com"
    body = resp.json()
    assert body["username"] == u.username
    assert body["email"] == u.email
    # Ensure initial password provided and meets minimum length
    min_initial_password_length = 8
    assert "initial_password" in body
    assert len(body["initial_password"]) >= min_initial_password_length


def test_autofill_handles_collision(auth_client):
    # First Jane Doe
    r1 = _post_onboard(
        auth_client,
        {"first_name": "Jane", "last_name": "Doe"},
    )
    assert r1.status_code == HTTPStatus.CREATED
    # Second Jane Doe
    r2 = _post_onboard(
        auth_client,
        {"first_name": "Jane", "last_name": "Doe"},
    )
    assert r2.status_code == HTTPStatus.CREATED
    user_model = get_user_model()
    usernames = list(
        user_model.objects.filter(first_name="Jane", last_name="Doe").values_list(
            "username", flat=True
        )
    )
    assert len(usernames) == EXPECTED_COLLISION_COUNT
    assert len(set(usernames)) == EXPECTED_COLLISION_COUNT, (
        "Usernames should be unique even with same first/last"
    )


def test_autofill_missing_names(auth_client):
    resp = _post_onboard(auth_client, {})
    assert resp.status_code == HTTPStatus.CREATED
    user_model = get_user_model()
    created = user_model.objects.order_by("-id").first()
    # Fallback: first initial 'u' + 'user' + sequence
    assert created.username.startswith("uuser")


def test_autofill_non_ascii(auth_client):
    resp = _post_onboard(
        auth_client,
        {"first_name": "José", "last_name": "Niño"},
    )
    assert resp.status_code == HTTPStatus.CREATED
    user_model = get_user_model()
    created = user_model.objects.order_by("-id").first()
    # Accents dropped; last name Niño -> nino truncated (default length 6)
    assert created.username.startswith("jnino")
