from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from hr_payroll.attendance.models import Attendance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.org.models import Department
from hr_payroll.payroll.models import BankMaster
from tests.permissions.factories import RoleContext
from tests.permissions.factories import create_user_with_role
from tests.permissions.factories import ensure_groups

User = get_user_model()

ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_PAYROLL = "Payroll"
ROLE_LINE_MANAGER = "Line Manager"
ROLE_EMPLOYEE = "Employee"
RBAC_GROUPS = [ROLE_ADMIN, ROLE_MANAGER, ROLE_PAYROLL, ROLE_LINE_MANAGER, ROLE_EMPLOYEE]


class RoleAPITestCase(APITestCase):
    """Base test case to streamline RBAC fixtures and helpers."""

    def setUp(self):
        super().setUp()
        ensure_groups(RBAC_GROUPS)
        self.departments = {
            "hq": self._create_department("HQ"),
            "remote": self._create_department("Remote"),
        }
        self.roles: dict[str, RoleContext] = {}
        self.roles[ROLE_ADMIN] = create_user_with_role(
            "admin",
            groups=[ROLE_ADMIN],
            is_staff=True,
            department=self.departments["hq"],
        )
        self.roles[ROLE_MANAGER] = create_user_with_role(
            "manager",
            groups=[ROLE_MANAGER],
            department=self.departments["hq"],
        )
        self.roles[ROLE_PAYROLL] = create_user_with_role(
            "payroll",
            groups=[ROLE_PAYROLL],
            department=self.departments["hq"],
        )
        self.roles[ROLE_LINE_MANAGER] = create_user_with_role(
            "linemgr",
            groups=[ROLE_LINE_MANAGER],
            department=self.departments["hq"],
        )
        self.roles[ROLE_EMPLOYEE] = create_user_with_role(
            "employee",
            groups=[ROLE_EMPLOYEE],
            line_manager=self.roles[ROLE_LINE_MANAGER].employee,
            department=self.departments["hq"],
        )
        self.others = {
            "employee": create_user_with_role(
                "other",
                groups=[ROLE_EMPLOYEE],
                department=self.departments["remote"],
            )
        }
        self.departments["remote"].manager = self.roles[ROLE_MANAGER].employee
        self.departments["remote"].save(update_fields=["manager", "updated_at"])

        self.bank_master = BankMaster.objects.create(name="Bank A")
        self.leave_type = LeaveType.objects.create(
            name="Annual",
            color_code="#00FF00",
            description="Annual leave",
        )
        self.leave_policy = LeavePolicy.objects.create(
            leave_type=self.leave_type,
            name="Annual Policy",
            description="Policy",
            entitlement=10,
            max_carry_over=5,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )
        self.leave_requests = {
            "team": LeaveRequest.objects.create(
                employee=self.roles[ROLE_EMPLOYEE].employee,
                policy=self.leave_policy,
                start_date=timezone.now().date(),
                end_date=timezone.now().date(),
                duration=1,
            ),
            "other": LeaveRequest.objects.create(
                employee=self.others["employee"].employee,
                policy=self.leave_policy,
                start_date=timezone.now().date(),
                end_date=timezone.now().date(),
                duration=1,
            ),
        }
        self.attendance_records = {
            "team": Attendance.objects.create(
                employee=self.roles[ROLE_EMPLOYEE].employee,
                date=timezone.now().date(),
                clock_in=timezone.now(),
                clock_in_location="HQ kiosk",
            ),
            "other": Attendance.objects.create(
                employee=self.others["employee"].employee,
                date=timezone.now().date(),
                clock_in=timezone.now(),
                clock_in_location="Remote kiosk",
            ),
        }

    # Utilities -------------------------------------------------------------
    def _create_department(self, name: str):
        return Department.objects.create(name=name)

    def authenticate(self, role: str):
        self.client.force_authenticate(user=self.roles[role].user)

    def assert_http_status(self, response, expected_status: int):
        msg = getattr(response, "data", response)
        assert response.status_code == expected_status, msg

    def get(self, url_name: str, *, role: str, reverse_kwargs=None, **kwargs):
        self.authenticate(role)
        url = reverse(url_name, kwargs=reverse_kwargs)
        return self.client.get(url, **kwargs)

    def post(
        self, url_name: str, *, role: str, payload=None, reverse_kwargs=None, **kwargs
    ):
        self.authenticate(role)
        url = reverse(url_name, kwargs=reverse_kwargs)
        return self.client.post(url, data=payload or {}, format="json", **kwargs)

    def patch(
        self, url_name: str, *, role: str, payload=None, reverse_kwargs=None, **kwargs
    ):
        self.authenticate(role)
        url = reverse(url_name, kwargs=reverse_kwargs)
        return self.client.patch(url, data=payload or {}, format="json", **kwargs)

    def delete(self, url_name: str, *, role: str, reverse_kwargs=None, **kwargs):
        self.authenticate(role)
        url = reverse(url_name, kwargs=reverse_kwargs)
        return self.client.delete(url, **kwargs)

    def assert_allowed(self, response):
        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_204_NO_CONTENT,
        ), response.data

    def assert_denied(self, response, code=status.HTTP_403_FORBIDDEN):
        assert response.status_code == code, response.data

    def extract_results(self, response):
        data = response.data
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        return data if isinstance(data, list) else []
