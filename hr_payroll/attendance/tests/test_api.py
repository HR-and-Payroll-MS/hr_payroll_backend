import datetime as dt
import secrets
import string

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import OfficeNetwork
from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department
from hr_payroll.org.models import OrganizationPolicy
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
    assert att.status == Attendance.Status.PRESENT


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


@pytest.mark.django_db
def test_line_manager_cannot_edit_attendance_clock_times_but_manager_can():
    rand_pwd = "x" * 12

    # Department
    dept = Department.objects.create(name="Engineering")

    # Line manager user
    lm_user = User.objects.create_user(
        username="lm1", email="lm1@example.com", password=rand_pwd
    )
    lm_group, _ = Group.objects.get_or_create(name="Line Manager")
    lm_user.groups.add(lm_group)
    lm_emp = Employee.objects.create(user=lm_user, department=dept)

    # Employee in same department
    emp_user = User.objects.create_user(
        username="emp_lm", email="emp_lm@example.com", password=rand_pwd
    )
    employee = Employee.objects.create(
        user=emp_user, department=dept, line_manager=lm_emp
    )

    att = Attendance.objects.create(
        employee=employee,
        date=timezone.now().date(),
        clock_in=timezone.now() - dt.timedelta(hours=9),
        clock_in_location="HQ",
        clock_out=timezone.now() - dt.timedelta(hours=1),
        clock_out_location="HQ",
        work_schedule_hours=8,
        paid_time=dt.timedelta(hours=8),
    )

    # Line Manager should be forbidden from editing clock times/locations
    client = APIClient()
    client.force_authenticate(user=lm_user)
    res = client.patch(
        f"/api/v1/attendances/{att.pk}/",
        {"clock_in_location": "Remote"},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Manager can edit
    mgr_user = User.objects.create_user(
        username="mgr_edit", email="mgr_edit@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    mgr_user.groups.add(mgr_group)
    Employee.objects.create(user=mgr_user)

    client.force_authenticate(user=mgr_user)
    res2 = client.patch(
        f"/api/v1/attendances/{att.pk}/",
        {"clock_in_location": "Remote"},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK
    att.refresh_from_db()
    assert att.clock_in_location == "Remote"


@pytest.mark.django_db
def test_adjust_paid_time_requires_notes_when_policy_says_docs_required():
    OrganizationPolicy.objects.update_or_create(
        org_id=1,
        defaults={
            "document": {
                "attendancePolicy": {
                    "attendanceCorrection": {
                        "documentationRequired": {
                            "__type": "dropdown",
                            "options": ["Yes", "No"],
                            "value": "Yes",
                        }
                    }
                }
            }
        },
    )

    rand_pwd = "x" * 12
    manager_user = User.objects.create_user(
        username="mgr2", email="m2@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    manager_user.groups.add(mgr_group)
    manager_emp = Employee.objects.create(user=manager_user)

    emp_user = User.objects.create_user(
        username="emp2", email="e2@example.com", password=rand_pwd
    )
    employee = Employee.objects.create(user=emp_user, line_manager=manager_emp)

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
    res = client.post(
        f"/api/v1/attendances/{att.pk}/adjust-paid-time/",
        {"paid_time": "09:00:00"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "notes" in res.json()


@pytest.mark.django_db
def test_adjust_paid_time_rejects_overtime_when_overtime_not_allowed():
    OrganizationPolicy.objects.update_or_create(
        org_id=1,
        defaults={
            "document": {
                "attendancePolicy": {
                    "overtimeRules": {
                        "overtimeAllowed": {
                            "__type": "dropdown",
                            "options": ["Yes", "No"],
                            "value": "No",
                        }
                    }
                }
            }
        },
    )

    rand_pwd = "x" * 12
    manager_user = User.objects.create_user(
        username="mgr3", email="m3@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    manager_user.groups.add(mgr_group)
    manager_emp = Employee.objects.create(user=manager_user)

    emp_user = User.objects.create_user(
        username="emp3", email="e3@example.com", password=rand_pwd
    )
    employee = Employee.objects.create(user=emp_user, line_manager=manager_emp)

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
    res = client.post(
        f"/api/v1/attendances/{att.pk}/adjust-paid-time/",
        {"paid_time": "09:00:00", "notes": "manual fix"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_adjust_paid_time_applies_overtime_min_minutes_threshold():
    OrganizationPolicy.objects.update_or_create(
        org_id=1,
        defaults={
            "document": {
                "attendancePolicy": {
                    "overtimeRules": {
                        "overtimeAllowed": {
                            "__type": "dropdown",
                            "options": ["Yes", "No"],
                            "value": "Yes",
                        },
                        "minMinutes": 60,
                    }
                }
            }
        },
    )

    rand_pwd = "x" * 12
    manager_user = User.objects.create_user(
        username="mgr4", email="m4@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    manager_user.groups.add(mgr_group)
    manager_emp = Employee.objects.create(user=manager_user)

    emp_user = User.objects.create_user(
        username="emp4", email="e4@example.com", password=rand_pwd
    )
    employee = Employee.objects.create(user=emp_user, line_manager=manager_emp)

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
    # 30 minutes overtime (< 60) should clamp overtime_seconds to 0
    res = client.post(
        f"/api/v1/attendances/{att.pk}/adjust-paid-time/",
        {"paid_time": "08:30:00", "notes": "manual fix"},
        format="json",
    )
    assert res.status_code == status.HTTP_201_CREATED
    att.refresh_from_db()
    assert att.overtime_seconds == 0


@pytest.mark.django_db
def test_employee_clock_out_today_endpoint_does_not_require_attendance_id():
    rand_pwd = "x" * 12
    user = User.objects.create_user(
        username="u_clockout", email="u_clockout@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)
    today = timezone.now().date()
    Attendance.objects.create(
        employee=emp,
        date=today,
        clock_in=timezone.now() - dt.timedelta(hours=8),
        clock_in_location="HQ",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/v1/employees/{emp.id}/attendances/clock-out/",
        {"location": "HQ"},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    body = res.json()
    assert body["attendance_id"] is not None
    assert any(p["type"] == "check_out" for p in body["punches"])


@pytest.mark.django_db
def test_employee_clock_out_today_accepts_clock_out_location_and_clock_out_aliases():
    rand_pwd = "x" * 12
    user = User.objects.create_user(
        username="u_clockout2", email="u_clockout2@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)
    today = timezone.now().date()
    Attendance.objects.create(
        employee=emp,
        date=today,
        clock_in=timezone.now() - dt.timedelta(hours=8),
        clock_in_location="HQ",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/v1/employees/{emp.id}/attendances/clock-out/",
        {
            "clock_out_location": "HQ",
            "clock_out": (timezone.now()).isoformat(),
        },
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_employee_clock_in_accepts_only_clock_in_location_and_sets_time_server_side():
    rand_pwd = "x" * 12
    OfficeNetwork.objects.create(label="Loopback", cidr="127.0.0.1/32", is_active=True)

    user = User.objects.create_user(
        username="u_clockin", email="u_clockin@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)

    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/v1/employees/{emp.id}/attendances/clock-in/",
        {"clock_in_location": "HQ"},
        format="json",
        HTTP_X_FORWARDED_FOR="127.0.0.1",
    )
    assert res.status_code == status.HTTP_201_CREATED
    body = res.json()
    assert body.get("clock_in")


@pytest.mark.django_db
def test_employee_clock_in_accepts_location_alias():
    rand_pwd = "x" * 12
    OfficeNetwork.objects.create(label="Loopback", cidr="127.0.0.1/32", is_active=True)

    user = User.objects.create_user(
        username="u_clockin2", email="u_clockin2@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)

    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/v1/employees/{emp.id}/attendances/clock-in/",
        {"location": "HQ"},
        format="json",
        HTTP_X_FORWARDED_FOR="127.0.0.1",
    )
    assert res.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_hr_can_clear_clock_in_and_employee_can_clock_in_again_via_check_endpoint():
    rand_pwd = "x" * 12
    OfficeNetwork.objects.create(label="Loopback", cidr="127.0.0.1/32", is_active=True)

    mgr_user = User.objects.create_user(
        username="mgr_reset", email="mgr_reset@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    mgr_user.groups.add(mgr_group)
    Employee.objects.create(user=mgr_user)

    user = User.objects.create_user(
        username="u_reset", email="u_reset@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)
    today = timezone.now().date()

    att = Attendance.objects.create(
        employee=emp,
        date=today,
        clock_in=timezone.now() - dt.timedelta(hours=1),
        clock_in_location="HQ",
        clock_out=timezone.now() - dt.timedelta(minutes=30),
        clock_out_location="HQ",
    )

    # HR clears both clock_in and clock_out
    hr_client = APIClient()
    hr_client.force_authenticate(user=mgr_user)
    res = hr_client.patch(
        f"/api/v1/attendances/{att.pk}/",
        {
            "clock_in": None,
            "clock_out": None,
            "clock_in_location": "",
            "clock_out_location": "",
        },
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    # /today should now behave like there's no active attendance
    emp_client = APIClient()
    emp_client.force_authenticate(user=user)
    today_res = emp_client.get(f"/api/v1/employees/{emp.id}/attendances/today/")
    assert today_res.status_code == status.HTTP_200_OK
    assert today_res.json()["attendance_id"] is None

    # Employee can clock-in again via the check endpoint
    check_res = emp_client.post(
        f"/api/v1/employees/{emp.id}/attendances/check/",
        {"action": "check_in", "location": "HQ"},
        format="json",
        HTTP_X_FORWARDED_FOR="127.0.0.1",
    )
    assert check_res.status_code == status.HTTP_201_CREATED
    body = check_res.json()
    assert body["attendance_id"] is not None
    assert any(p["type"] == "check_in" for p in body["punches"])


@pytest.mark.django_db
def test_hr_can_clear_clock_out_and_employee_can_clock_out_later():
    rand_pwd = "x" * 12
    OfficeNetwork.objects.create(label="Loopback", cidr="127.0.0.1/32", is_active=True)

    mgr_user = User.objects.create_user(
        username="mgr_clearco", email="mgr_clearco@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    mgr_user.groups.add(mgr_group)
    Employee.objects.create(user=mgr_user)

    user = User.objects.create_user(
        username="u_clearco", email="u_clearco@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=user)
    today = timezone.now().date()

    att = Attendance.objects.create(
        employee=emp,
        date=today,
        clock_in=timezone.now() - dt.timedelta(hours=8),
        clock_in_location="HQ",
        clock_out=timezone.now() - dt.timedelta(hours=7),
        clock_out_location="HQ",
    )

    # HR clears clock_out to allow time to continue counting
    hr_client = APIClient()
    hr_client.force_authenticate(user=mgr_user)
    res = hr_client.patch(
        f"/api/v1/attendances/{att.pk}/",
        {"clock_out": None, "clock_out_location": ""},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    emp_client = APIClient()
    emp_client.force_authenticate(user=user)
    clock_out_res = emp_client.post(
        f"/api/v1/employees/{emp.id}/attendances/clock-out/",
        {"location": "HQ"},
        format="json",
    )
    assert clock_out_res.status_code == status.HTTP_200_OK
    payload = clock_out_res.json()
    assert payload["attendance_id"] is not None
    assert any(p["type"] == "check_out" for p in payload["punches"])


@pytest.mark.django_db
def test_hr_department_drilldown_creates_placeholder_attendance_ids_for_absent_employees():  # noqa: E501
    rand_pwd = "x" * 12

    # HR user
    mgr_user = User.objects.create_user(
        username="mgr_dept", email="mgr_dept@example.com", password=rand_pwd
    )
    mgr_group, _ = Group.objects.get_or_create(name="Manager")
    mgr_user.groups.add(mgr_group)
    mgr_emp = Employee.objects.create(user=mgr_user)

    # Department + employee without an Attendance row today
    dept = Department.objects.create(name="IT", is_active=True)
    emp_user = User.objects.create_user(
        username="emp_dept", email="emp_dept@example.com", password=rand_pwd
    )
    emp = Employee.objects.create(user=emp_user, department=dept, line_manager=mgr_emp)

    client = APIClient()
    client.force_authenticate(user=mgr_user)

    res = client.get(f"/api/v1/attendances/departments/{dept.id}/")
    assert res.status_code == status.HTTP_200_OK
    rows = res.json()
    assert isinstance(rows, list)
    row = next(r for r in rows if r["employee_id"] == emp.id)
    assert row["attendance_id"] is not None

    # HR can PATCH using the returned id (no /attendances/null/)
    patch = client.patch(
        f"/api/v1/attendances/{row['attendance_id']}/",
        {"notes": "created by drilldown"},
        format="json",
    )
    assert patch.status_code == status.HTTP_200_OK
