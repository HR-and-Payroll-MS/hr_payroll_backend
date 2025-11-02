import secrets

import pytest
from django.utils import timezone

from hr_payroll.attendance.models import Attendance
from hr_payroll.employees.models import Employee


@pytest.mark.django_db
def test_create_attendance(django_user_model):
    pwd = secrets.token_urlsafe(12)
    user = django_user_model.objects.create_user(username="u1", password=pwd)

    emp = Employee.objects.create(user=user)
    a = Attendance.objects.create(
        employee=emp,
        date=timezone.now().date(),
        clock_in=timezone.now(),
        clock_in_location="Office",
        work_schedule_hours=8,
        paid_time=timezone.timedelta(hours=8),
    )
    assert a.employee_id == emp.id
    assert a.logged_time is None
