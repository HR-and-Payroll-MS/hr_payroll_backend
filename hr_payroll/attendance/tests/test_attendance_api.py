from datetime import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from hr_payroll.attendance.api import views as attendance_api_views
from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.attendance.models import OfficeNetworkRange
from hr_payroll.employees.models import Employee
from hr_payroll.users.models import User


@pytest.fixture
def staff_client(db):
    user = User.objects.create_user(
        username="admin",
        email="admin@example.com",
        password="password",
        is_staff=True,
    )
    employee = Employee.objects.create(user=user, employee_id="EMP1")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, employee


def test_network_status_allows_matching_cidr(staff_client):
    client, employee = staff_client
    OfficeNetworkRange.objects.create(name="Office", cidr="127.0.0.1/32")

    response = client.get(
        f"/api/employees/{employee.id}/attendances/network-status/",
        REMOTE_ADDR="127.0.0.1",
    )

    assert response.status_code == 200
    assert response.data["allowed"] is True
    assert response.data["matched_range"] == "Office"


def test_clock_flow_applies_shift_and_paid_minutes(staff_client, monkeypatch):
    client, employee = staff_client

    dt_in = timezone.make_aware(datetime(2025, 1, 1, 9, 0))
    dt_out = timezone.make_aware(datetime(2025, 1, 1, 17, 0))
    times = iter([dt_in, dt_out])

    monkeypatch.setattr(
        attendance_api_views.timezone, "localtime", lambda *args, **kwargs: next(times)
    )
    monkeypatch.setattr(
        attendance_api_views.timezone, "localdate", lambda *args, **kwargs: dt_in.date()
    )

    resp_today = client.get(
        f"/api/employees/{employee.id}/attendances/today/",
    )
    assert resp_today.status_code == 200

    resp_in = client.post(
        f"/api/employees/{employee.id}/attendances/clock-in/",
        {"location": "onsite"},
        format="json",
    )
    assert resp_in.status_code == 201

    resp_out = client.post(
        f"/api/employees/{employee.id}/attendances/clock-out/",
        {"location": "onsite"},
        format="json",
    )
    assert resp_out.status_code == 200

    record = AttendanceRecord.objects.get(employee=employee, date=dt_in.date())
    assert record.shift_name == "Day Shift"
    assert record.work_schedule_minutes == 480
    assert record.paid_minutes == 480
    assert record.clock_in.hour == 9
    assert record.clock_out.hour == 17
