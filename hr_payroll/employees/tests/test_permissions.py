import pytest


pytestmark = pytest.mark.skip(reason="employees app removed; tests skipped to start clean")
import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import EmployeeDocument


@pytest.mark.django_db
def test_setup_rbac_includes_employees_models_permissions():
    Group.objects.filter(name__in=["Admin", "Manager", "Employee"]).delete()
    call_command("setup_rbac")

    admin = Group.objects.get(name="Admin")
    manager = Group.objects.get(name="Manager")
    employee = Group.objects.get(name="Employee")

    # Expect each model to have view perms, admin should have add/change/delete too
    models = [Department, Employee, EmployeeDocument]
    for model in models:
        model_name = model._meta.model_name  # noqa: SLF001
        view_codename = f"view_{model_name}"

        assert admin.permissions.filter(codename=view_codename).exists()
        assert manager.permissions.filter(codename=view_codename).exists()
        assert employee.permissions.filter(codename=view_codename).exists()

        # Admin broader perms
        assert admin.permissions.filter(codename=f"add_{model_name}").exists()
        assert admin.permissions.filter(codename=f"change_{model_name}").exists()
        assert admin.permissions.filter(codename=f"delete_{model_name}").exists()

    # Employee should be able to add EmployeeDocument
    assert employee.permissions.filter(codename="add_employeedocument").exists()


@pytest.mark.django_db
def test_non_elevated_cannot_create_department_or_employee():
    user_model = get_user_model()
    user = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="low",
        email="l@example.com",
        password="x",  # noqa: S106
    )
    client = APIClient()
    client.force_authenticate(user=user)

    r = client.post("/api/v1/departments/", {"name": "X"}, format="json")
    assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)

    # Try creating an employee record for someone
    other = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="other",
        import pytest


        pytestmark = pytest.mark.skip(reason="employees app removed; tests skipped to start clean")
    assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
