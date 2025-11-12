from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from hr_payroll.org.models import Department

TEST_PASSWORD = "Admin!123"  # noqa: S105 test-only password constant


class TestUsernameEmailGeneration(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            password=TEST_PASSWORD,
        )
        self.admin.is_staff = True
        self.admin.save()
        self.client.force_authenticate(user=self.admin)

    def _register(self, dept):
        payload = {
            "first_name": "Alex",
            "last_name": "Smith",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "nationality": "Ethiopian",
            "department_id": dept.pk,
            "title": "Engineer",
            "join_date": "2025-11-01",
            "job_effective_date": "2025-11-01",
            "job_position_type": "IC",
            "job_employment_type": "fulltime",
            "contract_number": "C-XYZ",
            "contract_name": "FT",
            "contract_type": "permanent",
            "contract_start_date": "2025-11-01",
        }
        r = self.client.post("/api/v1/employees/register/", payload, format="json")
        assert r.status_code == status.HTTP_201_CREATED, r.data
        return r.data["credentials"]

    def test_usernames_and_emails_are_unique_and_verified(self):
        dept = Department.objects.create(name="ICT")
        c1 = self._register(dept)
        c2 = self._register(dept)
        # Salted usernames/emails differ even with same names
        assert c1["username"] != c2["username"]
        assert c1["email"] != c2["email"]
        # Emails are valid and verified/primary in allauth
        e1 = EmailAddress.objects.get(email=c1["email"])
        e2 = EmailAddress.objects.get(email=c2["email"])

        assert e1.verified
        assert e1.primary
        assert e2.verified
        assert e2.primary
