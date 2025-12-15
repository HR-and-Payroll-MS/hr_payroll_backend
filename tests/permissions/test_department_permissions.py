from rest_framework import status

from tests.permissions.mixins import ROLE_EMPLOYEE
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import RoleAPITestCase


class DepartmentPermissionTests(RoleAPITestCase):
    def test_create_department_requires_manager_or_admin(self):
        payload = {"name": "Operations"}
        denied = self.post(
            "api_v1:department-list",
            role=ROLE_EMPLOYEE,
            payload=payload,
        )
        self.assert_denied(denied)
        allowed = self.post(
            "api_v1:department-list",
            role=ROLE_MANAGER,
            payload=payload,
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)

    def test_assign_manager_requires_elevated_role(self):
        department = self.departments["remote"]
        target_employee_id = self.roles[ROLE_EMPLOYEE].employee.id
        denied = self.post(
            "api_v1:department-assign-manager",
            role=ROLE_EMPLOYEE,
            payload={"employee_id": target_employee_id},
            reverse_kwargs={"pk": department.pk},
        )
        self.assert_denied(denied)
        allowed = self.post(
            "api_v1:department-assign-manager",
            role=ROLE_MANAGER,
            payload={"employee_id": target_employee_id},
            reverse_kwargs={"pk": department.pk},
        )
        self.assert_http_status(allowed, status.HTTP_200_OK)
        department.refresh_from_db()
        assert department.manager_id == target_employee_id
