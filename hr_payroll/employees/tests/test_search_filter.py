from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from hr_payroll.employees.models import Employee
from hr_payroll.employees.models import JobHistory
from hr_payroll.org.models import Department
from hr_payroll.users.models import UserProfile

User = get_user_model()

TEST_PASSWORD = "password"  # noqa: S105 test-only password constant


class TestEmployeeSearchFilter(APITestCase):
    def setUp(self):
        # Create Admin user to perform searches (sees all)
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password=TEST_PASSWORD
        )
        self.admin.is_staff = True
        self.admin.save()
        Employee.objects.create(user=self.admin, is_active=True)

        # Departments
        self.deptA = Department.objects.create(name="DeptA")
        self.deptB = Department.objects.create(name="DeptB")

        # Employee 1: John Doe, Male, DeptA, Active, Fulltime
        self.u1 = User.objects.create_user(
            username="john",
            email="john@example.com",
            password=TEST_PASSWORD,
            first_name="John",
            last_name="Doe",
        )
        UserProfile.objects.create(user=self.u1, gender="Male")
        self.e1 = Employee.objects.create(
            user=self.u1, department=self.deptA, is_active=True
        )
        JobHistory.objects.create(
            employee=self.e1,
            effective_date="2023-01-01",
            job_title="Dev",
            employment_type="fulltime",
        )

        # Employee 2: Jane Smith, Female, DeptB, Active, Contract
        self.u2 = User.objects.create_user(
            username="jane",
            email="jane@test.com",
            password=TEST_PASSWORD,
            first_name="Jane",
            last_name="Smith",
        )
        UserProfile.objects.create(user=self.u2, gender="Female")
        self.e2 = Employee.objects.create(
            user=self.u2, department=self.deptB, is_active=True
        )
        JobHistory.objects.create(
            employee=self.e2,
            effective_date="2023-01-01",
            job_title="Designer",
            employment_type="contract",
        )

        # Employee 3: Bob Jones, Male, DeptA, Inactive, Parttime
        self.u3 = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password=TEST_PASSWORD,
            first_name="Bob",
            last_name="Jones",
        )
        UserProfile.objects.create(user=self.u3, gender="Male")
        self.e3 = Employee.objects.create(
            user=self.u3, department=self.deptA, is_active=False
        )
        JobHistory.objects.create(
            employee=self.e3,
            effective_date="2023-01-01",
            job_title="Tester",
            employment_type="parttime",
        )

        self.client.force_authenticate(user=self.admin)
        self.url = "/api/v1/employees/"

    def test_search_by_name(self):
        # Search "John"
        r = self.client.get(self.url, {"search": "John"})
        assert r.status_code == 200
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["general"]["emailaddress"] == "john@example.com"

    def test_search_by_email(self):
        # Search "example.com" (matches John and Bob + Admin)
        # Admin email is admin@example.com
        r = self.client.get(self.url, {"search": "example.com"})
        assert r.status_code == 200
        # Should be 3: Admin, John, Bob
        emails = {x["general"]["emailaddress"] for x in r.data["results"]}
        assert "john@example.com" in emails
        assert "bob@example.com" in emails
        assert "admin@example.com" in emails

    def test_filter_by_gender(self):
        # Filter Male (John, Bob)
        r = self.client.get(self.url, {"gender": "Male"})
        assert r.status_code == 200
        usernames = {
            x["general"]["fullname"] for x in r.data["results"]
        }  # fullname from general
        # user.name is "First Last"
        assert "John Doe" in usernames
        assert "Bob Jones" in usernames
        assert "Jane Smith" not in usernames

    def test_filter_by_department(self):
        # Filter DeptA (John, Bob)
        r = self.client.get(self.url, {"department": self.deptA.id})
        assert r.status_code == 200
        ids = {x["id"] for x in r.data["results"]}
        assert str(self.e1.id) in ids
        assert str(self.e3.id) in ids
        assert str(self.e2.id) not in ids

    def test_filter_by_status(self):
        # Filter Inactive (Bob)
        r = self.client.get(self.url, {"status": "False"})
        assert r.status_code == 200
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["general"]["emailaddress"] == "bob@example.com"

    def test_filter_by_employment_type(self):
        # Filter Contract (Jane)
        r = self.client.get(self.url, {"employment_type": "contract"})
        assert r.status_code == 200
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["general"]["emailaddress"] == "jane@test.com"
