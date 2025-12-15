from rest_framework import status

from hr_payroll.employees.models import Employee
from tests.permissions.mixins import ROLE_EMPLOYEE
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import ROLE_PAYROLL
from tests.permissions.mixins import RoleAPITestCase


class EmployeeDirectoryPermissionTests(RoleAPITestCase):
    def test_payroll_role_sees_every_employee(self):
        response = self.get("api_v1:employees-list", role=ROLE_PAYROLL)
        self.assert_http_status(response, status.HTTP_200_OK)
        assert len(self.extract_results(response)) == Employee.objects.count()

    def test_regular_employee_scoped_to_self(self):
        response = self.get("api_v1:employees-list", role=ROLE_EMPLOYEE)
        results = self.extract_results(response)
        assert len(results) == 1
        assert (
            results[0]["general"]["emailaddress"]
            == self.roles[ROLE_EMPLOYEE].user.email
        )

    def test_regular_employee_can_only_retrieve_self(self):
        my_employee_id = self.roles[ROLE_EMPLOYEE].employee.pk
        allowed = self.get(
            "api_v1:employees-detail",
            role=ROLE_EMPLOYEE,
            reverse_kwargs={"pk": my_employee_id},
        )
        self.assert_http_status(allowed, status.HTTP_200_OK)

        other_employee_id = self.others["employee"].employee.pk
        denied = self.get(
            "api_v1:employees-detail",
            role=ROLE_EMPLOYEE,
            reverse_kwargs={"pk": other_employee_id},
        )
        self.assert_http_status(denied, status.HTTP_404_NOT_FOUND)

    def test_registration_action_requires_manager(self):
        payload = {
            "first_name": "New",
            "last_name": "Hire",
        }
        denied = self.post(
            "api_v1:employees-register",
            role=ROLE_EMPLOYEE,
            payload=payload,
        )
        self.assert_denied(denied)
        allowed = self.post(
            "api_v1:employees-register",
            role=ROLE_MANAGER,
            payload=payload,
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)
        assert "credentials" in allowed.data
