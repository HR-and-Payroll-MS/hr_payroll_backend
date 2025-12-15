import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.attendance.models import OfficeNetwork
from hr_payroll.employees.models import Employee

User = get_user_model()


@pytest.mark.django_db
class TestOfficeNetworkCheck:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            password="password",  # noqa: S106
        )
        self.employee = Employee.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        # Create an office network
        OfficeNetwork.objects.create(cidr="192.168.1.0/24", label="Office WiFi")

    def test_check_network_allowed(self):
        # Simulate request from allowed IP
        url = f"/api/v1/employees/{self.employee.pk}/attendances/network-status/"
        response = self.client.get(url, headers={"x-forwarded-for": "192.168.1.100"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_office_network"] is True
        assert response.data["ip"] == "192.168.1.100"
        assert response.data["employee"] == self.employee.pk

    def test_check_network_disallowed(self):
        # Simulate request from disallowed IP
        url = f"/api/v1/employees/{self.employee.pk}/attendances/network-status/"
        response = self.client.get(url, headers={"x-forwarded-for": "10.0.0.5"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_office_network"] is False
        assert response.data["ip"] == "10.0.0.5"
        assert response.data["employee"] == self.employee.pk

    def test_check_network_remote_addr(self):
        # Test fallback to REMOTE_ADDR
        # APIClient uses REMOTE_ADDR by default if not specified otherwise in extract
        # But here we pass it explicitly to client.get triggers
        # Note: APIClient might default REMOTE_ADDR to 127.0.0.1
        url = f"/api/v1/employees/{self.employee.pk}/attendances/network-status/"
        response = self.client.get(url, REMOTE_ADDR="192.168.1.50")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_office_network"] is True
        assert response.data["ip"] == "192.168.1.50"
        assert response.data["employee"] == self.employee.pk
