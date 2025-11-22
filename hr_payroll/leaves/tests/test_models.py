import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import BalanceHistory
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday

User = get_user_model()


@pytest.mark.django_db
class TestLeaveType:
    def test_create_leave_type(self):
        lt = LeaveType.objects.create(
            name="Annual",
            is_paid=True,
            unit="Days",
            color_code="#00FF00",
            description="Standard annual leave",
        )
        assert lt.name == "Annual"
        assert lt.is_paid is True
        assert lt.unit == "Days"
        assert lt.color_code == "#00FF00"

    def test_name_uniqueness(self):
        LeaveType.objects.create(name="Sick")
        with pytest.raises(IntegrityError):
            LeaveType.objects.create(name="Sick")

    def test_unit_choices(self):
        lt = LeaveType(name="Test", unit="Invalid")
        with pytest.raises(ValidationError):
            lt.full_clean()


@pytest.mark.django_db
class TestLeavePolicy:
    def setup_method(self):
        self.lt = LeaveType.objects.create(name="Annual", unit="Days")

    def test_create_policy(self):
        policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Senior Annual",
            assign_schedule="On Joining",
            accrual_frequency="Yearly",
            entitlement=12.00,
            max_carry_over=5.00,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
            eligibility_gender="All",
        )
        assert policy.leave_type == self.lt
        assert policy.entitlement == 12.00
        assert policy.is_active is True  # Default

    def test_carry_over_expire_validation(self):
        policy = LeavePolicy(
            leave_type=self.lt,
            name="Invalid Date",
            entitlement=10,
            carry_over_expire_month=13,  # Invalid
            carry_over_expire_day=32,  # Invalid
        )
        with pytest.raises(ValidationError):
            policy.full_clean()


@pytest.mark.django_db
class TestPublicHoliday:
    def test_create_holiday(self):
        ph = PublicHoliday.objects.create(
            name="New Year", start_date="2025-01-01", end_date="2025-01-01", year=2025
        )
        assert ph.name == "New Year"
        assert ph.year == 2025


@pytest.mark.django_db
class TestEmployeeBalance:
    def setup_method(self):
        self.user = User.objects.create_user(username="emp1", password="password")  # noqa: S106
        self.employee = Employee.objects.create(user=self.user)
        self.lt = LeaveType.objects.create(name="Annual", unit="Days")
        self.policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Standard",
            entitlement=20,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )

    def test_create_balance(self):
        balance = EmployeeBalance.objects.create(
            employee=self.employee,
            policy=self.policy,
            entitled_days=20.00,
            used_days=5.00,
            pending_days=2.00,
            carry_forward_days=0.00,
        )
        assert balance.employee == self.employee
        assert balance.policy == self.policy
        assert balance.available_days == 13.00  # 20 - 5 - 2


@pytest.mark.django_db
class TestLeaveRequest:
    def setup_method(self):
        self.user = User.objects.create_user(username="emp1", password="password")  # noqa: S106
        self.employee = Employee.objects.create(user=self.user)
        self.lt = LeaveType.objects.create(name="Annual", unit="Days")
        self.policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Standard",
            entitlement=20,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )

    def test_create_request(self):
        req = LeaveRequest.objects.create(
            employee=self.employee,
            policy=self.policy,
            start_date="2025-06-01",
            end_date="2025-06-05",
            duration=5.00,
            status="Pending",
        )
        assert req.status == "Pending"
        assert req.duration == 5.00

    def test_date_validation(self):
        req = LeaveRequest(
            employee=self.employee,
            policy=self.policy,
            start_date="2025-06-05",
            end_date="2025-06-01",  # End before start
            duration=5.00,
        )
        with pytest.raises(ValidationError):
            req.full_clean()


@pytest.mark.django_db
class TestBalanceHistory:
    def setup_method(self):
        self.user = User.objects.create_user(username="emp1", password="password")  # noqa: S106
        self.employee = Employee.objects.create(user=self.user)
        self.lt = LeaveType.objects.create(name="Annual", unit="Days")
        self.policy = LeavePolicy.objects.create(
            leave_type=self.lt,
            name="Standard",
            entitlement=20,
            carry_over_expire_month=12,
            carry_over_expire_day=31,
        )

    def test_create_history(self):
        hist = BalanceHistory.objects.create(
            employee=self.employee,
            policy=self.policy,
            event_type="Accrual",
            date="2025-01-01",
            change_amount=10.00,
            changed_by=self.user,
        )
        assert hist.change_amount == 10.00
        assert hist.event_type == "Accrual"
