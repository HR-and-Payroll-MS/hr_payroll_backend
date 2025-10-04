from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def manager_user(django_user_model):
    user = django_user_model.objects.create_user(
        username="mgr",
        email="mgr@example.com",
        password="manager-pass-123",  # noqa: S106
        first_name="Man",
        last_name="Age",
    )
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def auth_client(api_client, manager_user):
    api_client.force_authenticate(user=manager_user)
    return api_client


def _onboard(client, payload):
    return client.post("/api/v1/employees/onboard/new/", payload, format="json")


def test_initial_credentials_retrievable_then_expire(auth_client, settings):
    settings.ONBOARDING_CREDENTIAL_TTL_MINUTES = 1  # short TTL for test
    r = _onboard(auth_client, {"first_name": "Alice", "last_name": "Wonder"})
    assert r.status_code == HTTPStatus.CREATED, r.content
    body = r.json()
    emp_id = body["id"]
    user_username = body["user"]["username"]
    # Retrieve via endpoint
    get_r = auth_client.get(f"/api/v1/employees/{emp_id}/initial-credentials/")
    assert get_r.status_code == HTTPStatus.OK
    cred = get_r.json()
    assert cred["username"] == user_username
    assert "initial_password" in cred
    # Simulate expiry by deleting cache key
    # Derive the cache key explicitly (avoid overly long ternary expression)
    user_dict = body.get("user")
    cache_key = None
    if isinstance(user_dict, dict):
        cache_key = f"onboarding:cred:{user_dict['id']}"
    if cache_key is not None:
        cache.delete(cache_key)
    get_r2 = auth_client.get(f"/api/v1/employees/{emp_id}/initial-credentials/")
    assert get_r2.status_code == HTTPStatus.NOT_FOUND


def test_regenerate_credentials(auth_client):
    r = _onboard(auth_client, {"first_name": "Bob", "last_name": "Builder"})
    assert r.status_code == HTTPStatus.CREATED
    emp_id = r.json()["id"]
    first_creds = r.json()["credentials"]
    regen_r = auth_client.post(
        f"/api/v1/employees/{emp_id}/regenerate-credentials/", {}
    )
    assert regen_r.status_code == HTTPStatus.OK
    new_creds = regen_r.json()
    assert new_creds["username"] == first_creds["username"]
    assert new_creds["email"] == first_creds["email"]
    assert new_creds["initial_password"] != first_creds["initial_password"]


def test_regular_employee_cannot_access(auth_client, django_user_model):
    # Create a normal employee
    onboard = _onboard(auth_client, {"first_name": "Carl", "last_name": "Jones"})
    assert onboard.status_code == HTTPStatus.CREATED
    emp_id = onboard.json()["id"]
    # Create a non-staff user and authenticate as them
    user_model = get_user_model()
    normal_user = user_model.objects.create_user(
        username="norm",
        email="norm@example.com",
        password="pass",  # noqa: S106
    )
    dept = Department.objects.create(name="Ops")
    Employee.objects.create(user=normal_user, department=dept)
    c = APIClient()
    c.force_authenticate(user=normal_user)
    resp = c.get(f"/api/v1/employees/{emp_id}/initial-credentials/")
    assert resp.status_code in (HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND)
    resp2 = c.post(f"/api/v1/employees/{emp_id}/regenerate-credentials/", {})
    assert resp2.status_code in (HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND)
