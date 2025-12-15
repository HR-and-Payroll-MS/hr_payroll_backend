"""Integration-style permission tests covering core RBAC scenarios."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from hr_payroll.attendance.models import Attendance
from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.org.models import Department
from hr_payroll.payroll.models import BankMaster

RBAC_GROUPS = ["Admin", "Manager", "Payroll", "Line Manager", "Employee"]
TEST_PASSWORD = "TestPass123!"  # noqa: S105 - test credentials only


class PermissionMatrixAPITests(APITestCase):
    """Validate the most important role-based permission flows."""

    def setUp(self):
        self.user_model = get_user_model()
        for name in RBAC_GROUPS:
            Group.objects.get_or_create(name=name)
        self.dept_hq = Department.objects.create(name="HQ")
        self.dept_remote = Department.objects.create(name="Remote")
        self.admin_user, self.admin_employee = self._create_user(
            "admin",
            is_staff=True,
            groups=["Admin"],
        )
        self.manager_user, self.manager_employee = self._create_user(
            "manager",
            groups=["Manager"],
        )
        self.dept_remote.manager = self.manager_employee
        self.dept_remote.save(update_fields=["manager", "updated_at"])
        self.payroll_user, self.payroll_employee = self._create_user(
            "payroll",
            groups=["Payroll"],
        )
        self.line_manager_user, self.line_manager_employee = self._create_user(
            "linemgr",
            groups=["Line Manager"],
        )
        self.employee_user, self.employee_employee = self._create_user(
            "employee",
            line_manager=self.line_manager_employee,
        )
        self.other_employee_user, self.other_employee_employee = self._create_user(
            "other",
            department=self.dept_remote,
        )
        self.bank = BankMaster.objects.create(name="Bank A")
        self.leave_type = LeaveType.objects.create(
            name="Annual",
            color_code="#00FF00",
            description="Annual leave",
        )
        self.leave_policy = LeavePolicy.objects.create(
            leave_type=self.leave_type,
            name="Annual Policy",
            description="Base policy",
            entitlement=10,
            max_carry_over=5,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )
        self.leave_direct = LeaveRequest.objects.create(
            employee=self.employee_employee,
            policy=self.leave_policy,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            duration=1,
        )
        self.leave_other = LeaveRequest.objects.create(
            employee=self.other_employee_employee,
            policy=self.leave_policy,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            duration=1,
        )
        self.attendance_self = Attendance.objects.create(
            employee=self.employee_employee,
            date=timezone.now().date(),
            clock_in=timezone.now(),
            clock_in_location="HQ kiosk",
        )
        self.attendance_other = Attendance.objects.create(
            employee=self.other_employee_employee,
            date=timezone.now().date(),
            clock_in=timezone.now(),
            clock_in_location="Remote kiosk",
        )

    # Helpers -----------------------------------------------------------------
    def _create_user(
        self,
        username,
        *,
        groups=None,
        is_staff=False,
        department=None,
        line_manager=None,
    ):
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=TEST_PASSWORD,
        )
        if is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        for group_name in groups or []:
            user.groups.add(Group.objects.get(name=group_name))
        employee = Employee.objects.create(
            user=user,
            department=department or self.dept_hq,
            line_manager=line_manager,
            is_active=True,
        )
        return user, employee

    def _extract_results(self, response):
        data = response.data
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        return data if isinstance(data, list) else []

    # Tests --------------------------------------------------------------------
    def test_regular_employee_sees_only_their_attendance_records(self):
        url = reverse(
            "employee-attendance-list",
            kwargs={"employee_id": self.employee_employee.pk},
        )
        self.client.force_authenticate(user=self.employee_user)
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        employees = {row["employee"] for row in self._extract_results(resp)}
        assert employees == {self.employee_employee.pk}

    def test_admin_attendance_list_blocked_for_regular_employee(self):
        url = reverse("api_v1:attendance-list")
        self.client.force_authenticate(user=self.employee_user)
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_manual_entry_uses_authenticated_user_profile(self):
        url = reverse(
            "employee-attendance-manual-entry",
            kwargs={"employee_id": self.employee_employee.pk},
        )
        target_date = (timezone.now().date() + timedelta(days=7)).isoformat()
        target_clock_in = (timezone.now() + timedelta(days=7)).isoformat()
        payload = {
            "employee": self.manager_employee.pk,
            "date": target_date,
            "clock_in": target_clock_in,
            "clock_in_location": "HQ kiosk",
        }
        self.client.force_authenticate(user=self.employee_user)
        allowed = self.client.post(url, payload, format="json")
        assert allowed.status_code == status.HTTP_201_CREATED
        assert allowed.data["employee"] == self.employee_employee.pk

    def test_payroll_endpoints_only_allow_admin_or_payroll_roles(self):
        url = "/api/v1/payroll/banks/"
        self.client.force_authenticate(user=self.manager_user)
        denied = self.client.get(url)
        assert denied.status_code == status.HTTP_403_FORBIDDEN
        self.client.force_authenticate(user=self.payroll_user)
        allowed = self.client.get(url)
        assert allowed.status_code == status.HTTP_200_OK
        names = {row["name"] for row in self._extract_results(allowed)}
        assert self.bank.name in names

    def test_payroll_role_can_view_full_employee_directory(self):
        total_employees = Employee.objects.count()
        self.client.force_authenticate(user=self.payroll_user)
        resp = self.client.get("/api/v1/employees/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(self._extract_results(resp)) == total_employees
        self.client.force_authenticate(user=self.employee_user)
        scoped = self.client.get("/api/v1/employees/")
        assert len(self._extract_results(scoped)) == 1

    def test_line_manager_sees_only_team_leave_requests(self):
        url = "/api/v1/leaves/requests/"
        self.client.force_authenticate(user=self.line_manager_user)
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        employees = {row["employee"] for row in self._extract_results(resp)}
        assert self.employee_employee.pk in employees
        assert self.other_employee_employee.pk not in employees

    def test_department_management_locked_to_admin_and_managers(self):
        url = reverse("api_v1:department-list")
        payload = {"name": "New Dept"}
        self.client.force_authenticate(user=self.employee_user)
        denied = self.client.post(url, payload, format="json")
        assert denied.status_code == status.HTTP_403_FORBIDDEN
        self.client.force_authenticate(user=self.manager_user)
        allowed = self.client.post(url, payload, format="json")
        assert allowed.status_code == status.HTTP_201_CREATED
