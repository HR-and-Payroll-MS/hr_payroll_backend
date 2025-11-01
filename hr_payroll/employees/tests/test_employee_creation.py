import pytest


pytestmark = pytest.mark.skip(reason="employees app removed; tests skipped to start clean")
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.employees.models import Employee


@pytest.mark.django_db
def test_admin_can_create_employee_by_username():
    user_model = get_user_model()
    admin = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="adminx",
        email="ax@example.com",
        password="x",  # noqa: S106
        is_staff=True,
    )
    target = user_model.objects.create_user(  # type: ignore[attr-defined]
        import pytest


        pytestmark = pytest.mark.skip(reason="employees app removed; tests skipped to start clean")
    target = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="empdup",
        email="empdup@example.com",
        password="x",  # noqa: S106
    )
    Employee.objects.create(user=target)

    client = APIClient()
    client.force_authenticate(user=admin)

    r = client.post(
        "/api/v1/employees/onboard/existing/", {"user": target.username}, format="json"
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "user" in r.data


@pytest.mark.django_db
def test_non_elevated_cannot_create_employee():
    user_model = get_user_model()
    user = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="lowx",
        email="lowx@example.com",
        password="x",  # noqa: S106
    )
    other = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="someone",
        email="s@example.com",
        password="x",  # noqa: S106
    )

    client = APIClient()
    client.force_authenticate(user=user)

    r = client.post(
        "/api/v1/employees/onboard/existing/", {"user": other.username}, format="json"
    )
    assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
