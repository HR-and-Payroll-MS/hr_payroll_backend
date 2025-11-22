import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType

User = get_user_model()
TEST_PASSWORD = "password"  # noqa: S105


@pytest.mark.django_db
class TestLeaveAPI:
    def setup_method(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=TEST_PASSWORD
        )
        self.user = User.objects.create_user(
            username="emp1", email="emp1@example.com", password=TEST_PASSWORD
        )
        self.employee = Employee.objects.create(user=self.user)

        self.lt = LeaveType.objects.create(name="Annual", unit="Days")
        self.policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Standard",
            entitlement=20,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )

    def test_leave_type_crud_admin(self):
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.post(
            "/api/v1/leaves/types/",
            {"name": "Sick", "is_paid": True, "unit": "Days", "color_code": "#FF0000"},
        )
        assert res.status_code == 201
        assert res.data["name"] == "Sick"

    def test_leave_type_forbidden_user(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post(
            "/api/v1/leaves/types/",
            {"name": "Sick", "is_paid": True, "unit": "Days", "color_code": "#FF0000"},
        )
        assert res.status_code == 403

    def test_leave_request_create(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post(
            "/api/v1/leaves/requests/",
            {
                "policy": self.policy.id,
                "start_date": "2025-06-01",
                "end_date": "2025-06-05",
                "duration": 5.00,
            },
        )
        assert res.status_code == 201
        assert res.data["status"] == "Pending"
        assert LeaveRequest.objects.filter(employee=self.employee).exists()

    def test_balance_visibility(self):
        EmployeeBalance.objects.create(
            employee=self.employee, policy=self.policy, entitled_days=20
        )
        self.client.force_authenticate(user=self.user)
        res = self.client.get("/api/v1/leaves/employee-balances/")
        assert res.status_code == 200
        assert len(res.data["results"]) == 1
