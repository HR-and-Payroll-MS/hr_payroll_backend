from django.utils import timezone
from rest_framework import status

from tests.permissions.mixins import ROLE_EMPLOYEE
from tests.permissions.mixins import ROLE_LINE_MANAGER
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import RoleAPITestCase


class LeavePermissionTests(RoleAPITestCase):
    def test_manager_sees_all_leave_requests(self):
        response = self.get("api_v1:leave-request-list", role=ROLE_MANAGER)
        self.assert_http_status(response, status.HTTP_200_OK)
        employees = {row["employee"] for row in self.extract_results(response)}
        assert employees == {
            self.roles[ROLE_EMPLOYEE].employee.id,
            self.others["employee"].employee.id,
        }

    def test_line_manager_only_sees_team_requests(self):
        response = self.get("api_v1:leave-request-list", role=ROLE_LINE_MANAGER)
        self.assert_http_status(response, status.HTTP_200_OK)
        employees = {row["employee"] for row in self.extract_results(response)}
        assert self.roles[ROLE_EMPLOYEE].employee.id in employees
        assert self.others["employee"].employee.id not in employees

    def test_employee_can_submit_own_leave_request(self):
        payload = {
            "policy": self.leave_policy.id,
            "start_date": timezone.now().date().isoformat(),
            "end_date": timezone.now().date().isoformat(),
            "duration": 1,
        }
        response = self.post(
            "api_v1:leave-request-list",
            role=ROLE_EMPLOYEE,
            payload=payload,
        )
        self.assert_http_status(response, status.HTTP_201_CREATED)
        assert response.data["employee"] == self.roles[ROLE_EMPLOYEE].employee.id
