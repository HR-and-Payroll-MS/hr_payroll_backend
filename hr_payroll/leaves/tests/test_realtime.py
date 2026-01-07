import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType

User = get_user_model()
TEST_PASSWORD = "password"  # noqa: S105


@pytest.mark.django_db
class TestLeaveRealtime:
    def setup_method(self):
        self.client = APIClient()
        # Base leave type/policy
        self.lt = LeaveType.objects.create(name="Annual", unit="Days")
        self.policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Standard",
            entitlement=20,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )
        # Create approver group and users
        Group.objects.get_or_create(name="Line Manager")
        Group.objects.get_or_create(name="Admin")

        # Employee requesting leave
        self.user = User.objects.create_user(
            username="emp1", email="emp1@example.com", password=TEST_PASSWORD
        )
        self.employee = Employee.objects.create(user=self.user)

        # Line manager approver
        self.lm_user = User.objects.create_user(
            username="lmgr", email="lmgr@example.com", password=TEST_PASSWORD
        )
        self.lm_user.groups.add(Group.objects.get(name="Line Manager"))
        self.lm_employee = Employee.objects.create(user=self.lm_user)
        # Set employee's line manager
        self.employee.line_manager = self.lm_employee
        self.employee.save(update_fields=["line_manager", "updated_at"])

        # Admin user for escalation path
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password=TEST_PASSWORD,
        )
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.admin_emp = Employee.objects.create(user=self.admin)

    def test_leave_create_emits_to_assigned_approver(self, monkeypatch):
        # Authenticate as employee
        self.client.force_authenticate(user=self.user)

        calls = []

        def fake_emit_event_to_employee(employee_id, event, payload):
            calls.append((employee_id, event, payload))

        # Patch the symbol imported in views module
        monkeypatch.setattr(
            "hr_payroll.leaves.api.views.emit_event_to_employee",
            fake_emit_event_to_employee,
        )

        res = self.client.post(
            "/api/v1/leaves/requests/",
            {
                "policy": self.policy.id,
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "duration": 3.00,
                "employee_id": self.employee.id,
                "assigned_approver": self.lm_employee.id,
            },
        )
        assert res.status_code == 201, res.data
        assert len(calls) == 1
        employee_id, event, payload = calls[0]
        assert employee_id == self.lm_employee.id
        assert event == "leave.request.created"
        assert payload.get("id") == res.data.get("id")
        assert payload.get("approverIds") == [self.lm_employee.id]

    def test_leave_status_update_emits_to_employee_and_escalates(self, monkeypatch):
        # Create a pending request
        req = LeaveRequest.objects.create(
            employee=self.employee,
            policy=self.policy,
            start_date="2025-06-01",
            end_date="2025-06-01",
            duration=1.00,
            status=LeaveRequest.Status.PENDING,
        )

        # Authenticate as line manager (approving)
        self.client.force_authenticate(user=self.lm_user)

        emp_calls = []
        group_calls = []

        def fake_emit_event_to_employee(employee_id, event, payload):
            emp_calls.append((employee_id, event, payload))

        def fake_emit_event_to_group(group_name, event, payload):
            group_calls.append((group_name, event, payload))

        monkeypatch.setattr(
            "hr_payroll.leaves.api.views.emit_event_to_employee",
            fake_emit_event_to_employee,
        )
        monkeypatch.setattr(
            "hr_payroll.leaves.api.views.emit_event_to_group",
            fake_emit_event_to_group,
        )

        res = self.client.patch(
            f"/api/v1/leaves/requests/{req.id}/",
            {"status": LeaveRequest.Status.APPROVED},
            format="json",
        )
        assert res.status_code == 200, res.data

        # One call to employee with status update
        assert len(emp_calls) == 1
        emp_id, event, payload = emp_calls[0]
        assert emp_id == self.employee.id
        assert event == "leave.request.status"
        assert payload.get("status") == LeaveRequest.Status.APPROVED

        # Escalation to Admin group
        assert ("Admin", "leave.request.escalated", payload) in group_calls
