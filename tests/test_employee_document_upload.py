import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from hr_payroll.employees.models import Employee
from hr_payroll.users.models import User


@pytest.mark.django_db
def test_employee_upload_document_multipart_tempfile_no_deepcopy_error(
    settings, tmp_path
):
    """Uploading via multipart should not crash with deepcopy/pickle errors.

    Django can store uploaded files as TemporaryUploadedFile (BufferedRandom-backed)
    when the upload exceeds FILE_UPLOAD_MAX_MEMORY_SIZE. Historically, copying
    request.data for multipart requests could trigger:
    TypeError: cannot pickle 'BufferedRandom' instances
    """

    # Ensure uploads always write to a writable location (CI containers may not
    # have permissions for the default /app/hr_payroll/media).
    settings.MEDIA_ROOT = str(tmp_path / "media")

    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 1  # force temp-file uploads

    user = User.objects.create_user(
        username="docuser",
        email="docuser@example.com",
        password="testpass123",  # noqa: S106
    )
    employee = Employee.objects.create(user=user, employee_id="E-DOCTEST", title="Eng")

    client = APIClient()
    client.force_authenticate(user=user)

    upload = SimpleUploadedFile(
        "big.pdf",
        b"x" * 2048,
        content_type="application/pdf",
    )

    res = client.post(
        f"/api/v1/employees/{employee.pk}/upload-document/",
        data={"name": "Passport", "file": upload},
        format="multipart",
    )

    assert res.status_code == 201
    assert res.data["name"] == "Passport"
    assert "id" in res.data
    assert res.data.get("employee") in (employee.pk, str(employee.pk))


@pytest.mark.django_db
def test_employee_upload_document_accepts_frontend_alias_fields(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 1  # force temp-file uploads

    user = User.objects.create_user(
        username="docuser2",
        email="docuser2@example.com",
        password="testpass123",  # noqa: S106
    )
    employee = Employee.objects.create(user=user, employee_id="E-DOCTEST2", title="Eng")

    client = APIClient()
    client.force_authenticate(user=user)

    upload = SimpleUploadedFile(
        "alias.pdf",
        b"x" * 2048,
        content_type="application/pdf",
    )

    res = client.post(
        f"/api/v1/employees/{employee.pk}/upload-document/",
        data={"document_name": "Passport", "documents": upload},
        format="multipart",
    )

    assert res.status_code == 201
    assert res.data["name"] == "Passport"


@pytest.mark.django_db
def test_employee_upload_document_missing_file_returns_clear_400(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    user = User.objects.create_user(
        username="docuser3",
        email="docuser3@example.com",
        password="testpass123",  # noqa: S106
    )
    employee = Employee.objects.create(user=user, employee_id="E-DOCTEST3", title="Eng")

    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/v1/employees/{employee.pk}/upload-document/",
        data={"name": "Passport"},
        format="multipart",
    )

    assert res.status_code == 400
    assert res.data.get("code") == "MISSING_FILE"
    assert "accepted_fields" in res.data
