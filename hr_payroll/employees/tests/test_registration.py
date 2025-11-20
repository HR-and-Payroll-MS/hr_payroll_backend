from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department

TEST_PASSWORD = "Admin!123"  # noqa: S105 test-only password constant


class TestEmployeeRegistration(APITestCase):
    def setUp(self):
        # Auth as staff manager to call endpoint if required by permissions
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            password=TEST_PASSWORD,
        )
        self.admin.is_staff = True
        self.admin.save()
        self.client.force_authenticate(user=self.admin)

    def test_register_employee_creates_user_and_returns_credentials(self):
        dept = Department.objects.create(name="ICT")
        payload = {
            "first_name": "Eyob",
            "last_name": "Taye",
            "gender": "Male",
            "date_of_birth": "1995-01-01",
            "phone": "+251911234567",
            "nationality": "Ethiopian",
            "health_care": "Plan A",
            "marital_status": "Single",
            "personal_tax_id": "TIN1",
            "social_insurance": "PEN1",
            "department_id": dept.pk,
            "office": "HQ",
            "time_zone": "Africa/Addis_Ababa",
            "title": "Engineer",
            "join_date": "2025-11-01",
            "job_effective_date": "2025-11-01",
            "job_position_type": "IC",
            "job_employment_type": "fulltime",
            "contract_number": "C-1",
            "contract_name": "Fulltime",
            "contract_type": "permanent",
            "contract_start_date": "2025-11-01",
            "components": [
                {"kind": "recurring", "amount": "1000.00", "label": "Allowance"}
            ],
            "dependents": [
                {"name": "Sam", "relationship": "Child", "date_of_birth": "2015-06-15"}
            ],
            "bank_name": "ACME",
            "account_name": "Payroll",
            "account_number": "123456",
        }
        url = "/api/v1/employees/register/"
        r = self.client.post(url, payload, format="json")
        assert r.status_code == status.HTTP_201_CREATED, r.data
        # Credentials in response
        creds = r.data.get("credentials")
        assert creds is not None
        assert {"username", "email", "password"}.issubset(creds.keys())
        # Employee created and linked to user
        emp_id = r.data.get("job", {}).get("employeeid")
        assert emp_id
        emp = Employee.objects.get(employee_id=emp_id)
        assert emp.user.username == creds["username"]
        # Full detail fields present in nested structure
        assert "general" in r.data
        assert "job" in r.data
        assert "payroll" in r.data
        assert "documents" in r.data
        # Check specific nested fields
        assert r.data["general"]["fullname"]
        assert r.data["general"]["emailaddress"]
        assert r.data["job"]["jobtitle"]
        assert r.data["job"]["employmenttype"]
        assert r.data["payroll"]["employeestatus"]

    def test_missing_names_is_error(self):
        url = "/api/v1/employees/register/"
        r = self.client.post(url, {"title": "X"}, format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "first_name" in r.data
        assert "last_name" in r.data
