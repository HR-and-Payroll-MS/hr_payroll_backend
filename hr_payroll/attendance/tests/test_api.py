import datetime as dt
import secrets
import string

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.attendance.models import Attendance
from hr_payroll.employees.models import Employee
from hr_payroll.users.models import User


@pytest.mark.django_db
def test_manager_can_approve_direct_report_attendance():
    # Create manager and group
    rand_pwd = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
    )
    manager_user = User.objects.create_user(
        username="mgr", email="m@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    manager_user.groups.add(mgr_group)
    manager_emp = Employee.objects.create(user=manager_user)

    # Create employee reporting to manager
    emp_user = User.objects.create_user(
        username="emp", email="e@example.com", password=rand_pwd
    )
    employee = Employee.objects.create(user=emp_user, line_manager=manager_emp)

    # Create attendance (pending)
    att = Attendance.objects.create(
        employee=employee,
        date=timezone.now().date(),
        clock_in=timezone.now() - dt.timedelta(hours=9),
        clock_in_location="HQ",
        clock_out=timezone.now(),
        clock_out_location="HQ",
        work_schedule_hours=8,
        paid_time=dt.timedelta(hours=8),
    )

    client = APIClient()
    client.force_authenticate(user=manager_user)

    url = f"/api/v1/attendances/{att.pk}/approve/"
    res = client.post(url)
    assert res.status_code == status.HTTP_200_OK
    att.refresh_from_db()
    assert att.status == Attendance.Status.APPROVED


@pytest.mark.django_db
def test_my_summary_returns_totals():
    rand_pwd = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
    )
    user = User.objects.create_user(
        username="u1", email="u1@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)
    # Two days: one overtime, one deficit
    today = timezone.now().date()
    Attendance.objects.create(
        employee=emp,
        date=today - dt.timedelta(days=1),
        clock_in=timezone.now() - dt.timedelta(days=1, hours=9),
        clock_in_location="HQ",
        clock_out=timezone.now() - dt.timedelta(days=1),
        clock_out_location="HQ",
        work_schedule_hours=8,
        paid_time=dt.timedelta(hours=9),
    )
    Attendance.objects.create(
        employee=emp,
        date=today,
        clock_in=timezone.now() - dt.timedelta(hours=7),
        clock_in_location="HQ",
        clock_out=timezone.now(),
        clock_out_location="HQ",
        work_schedule_hours=8,
        paid_time=dt.timedelta(hours=7),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/v1/attendances/my/summary/")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "total_logged" in body
    assert "total_paid" in body
    assert "overtime" in body
    assert "deficit" in body
