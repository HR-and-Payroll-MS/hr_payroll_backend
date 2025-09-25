import io

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee


@pytest.mark.django_db
def test_department_crud_rbac():
    user_model = get_user_model()
    admin = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="admin1",
        email="a@example.com",
        password="x",  # noqa: S106
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin)

    # create
    r = client.post("/api/v1/departments/", {"name": "HR"}, format="json")
    assert r.status_code == status.HTTP_201_CREATED
    dept_id = r.data["id"]

    # list
    r = client.get("/api/v1/departments/")
    assert r.status_code == status.HTTP_200_OK
    assert any(d["id"] == dept_id for d in [{"id": x["id"]} for x in r.data]) or any(
        d.get("id") == dept_id for d in r.data
    )

    # update
    r = client.patch(
        f"/api/v1/departments/{dept_id}/",
        {"description": "People ops"},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK

    # non-elevated cannot create
    user = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="u1",
        email="u1@example.com",
        password="x",  # noqa: S106
    )
    client.force_authenticate(user=user)
    r = client.post("/api/v1/departments/", {"name": "IT"}, format="json")
    assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.django_db
def test_employee_visibility_and_docs_upload(tmp_path):
    user_model = get_user_model()
    admin = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="admin2",
        email="a2@example.com",
        password="x",  # noqa: S106
        is_staff=True,
    )
    user = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="emp1",
        email="e1@example.com",
        password="x",  # noqa: S106
    )
    other = user_model.objects.create_user(  # type: ignore[attr-defined]
        username="emp2",
        email="e2@example.com",
        password="x",  # noqa: S106
    )

    # create employee records
    d = Department.objects.create(name="Engineering")
    e1 = Employee.objects.create(user=user, department=d)
    Employee.objects.create(user=other, department=d)

    client = APIClient()
    # Regular employee sees only self
    client.force_authenticate(user=user)
    r = client.get("/api/v1/employees/")
    assert r.status_code == status.HTTP_200_OK
    assert len(r.data) == 1
    assert r.data[0]["user"] == user.username

    # Upload document (self)
    file_bytes = io.BytesIO(b"dummy")
    file_bytes.name = "contract.txt"
    r = client.post(
        "/api/v1/employee-documents/",
        {"employee": e1.id, "name": "contract", "file": file_bytes},
        format="multipart",
    )
    assert r.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK)

    # Admin sees all employees
    client.force_authenticate(user=admin)
    r = client.get("/api/v1/employees/")
    assert r.status_code == status.HTTP_200_OK
    assert len(r.data) >= 2  # noqa: PLR2004
