from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department


def create_group(name: str):
    Group.objects.get_or_create(name=name)


TEST_PASSWORD = "pass"  # noqa: S105 test-only password constant


class TestEmployeeRBACScoping(APITestCase):
    def setUp(self):
        create_group("Admin")
        create_group("Manager")
        create_group("Line Manager")
        user_model = get_user_model()
        # Departments
        self.deptA = Department.objects.create(name="DeptA")
        self.deptB = Department.objects.create(name="DeptB")
        # Admin user
        self.admin = user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            password=TEST_PASSWORD,
        )
        self.admin.is_staff = True
        self.admin.save()
        Employee.objects.create(user=self.admin, department=self.deptA, is_active=True)
        # Manager user (manages deptB)
        self.manager = user_model.objects.create_user(
            username="manager",
            email="manager@example.com",
            password=TEST_PASSWORD,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        mgr_emp = Employee.objects.create(
            user=self.manager, department=self.deptA, is_active=True
        )
        self.deptB.manager = mgr_emp
        self.deptB.save()
        # Line manager user
        self.line_manager = user_model.objects.create_user(
            username="linemgr",
            email="linemgr@example.com",
            password=TEST_PASSWORD,
        )
        self.line_manager.groups.add(Group.objects.get(name="Line Manager"))
        lm_emp = Employee.objects.create(
            user=self.line_manager, department=self.deptA, is_active=True
        )
        # Regular employee supervised by line manager
        self.emp1 = user_model.objects.create_user(
            username="emp1",
            email="emp1@example.com",
            password=TEST_PASSWORD,
        )
        Employee.objects.create(
            user=self.emp1, department=self.deptA, line_manager=lm_emp, is_active=True
        )
        # Employee in deptB
        self.emp2 = user_model.objects.create_user(
            username="emp2",
            email="emp2@example.com",
            password=TEST_PASSWORD,
        )
        Employee.objects.create(user=self.emp2, department=self.deptB, is_active=True)

    def _list(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get("/api/v1/employees/")

    def test_admin_sees_all(self):
        r = self._list(self.admin)
        expected_total = 5  # 1 admin + 1 manager + 1 line mgr + 2 regular
        assert len(r.data.get("results", [])) == expected_total

    def test_manager_sees_managed_dept_and_direct_reports(self):
        r = self._list(self.manager)
        usernames = {
            e["general"]["emailaddress"].split("@")[0]
            for e in r.data.get("results", [])
        }
        # Should include emp2 (deptB managed) and manager themselves
        # May not include emp1 (not direct report of manager)
        assert "emp2" in usernames
        assert "manager" in usernames

    def test_line_manager_sees_department_and_direct_reports(self):
        r = self._list(self.line_manager)
        usernames = {
            e["general"]["emailaddress"].split("@")[0]
            for e in r.data.get("results", [])
        }
        assert "emp1" in usernames  # direct report
        assert "linemgr" in usernames
        # Should not see emp2 from other department
        assert "emp2" not in usernames

    def test_regular_employee_sees_only_self(self):
        r = self._list(self.emp1)
        usernames = {
            e["general"]["emailaddress"].split("@")[0]
            for e in r.data.get("results", [])
        }
        assert usernames == {"emp1"}
