from rest_framework import status

from hr_payroll.payroll.models import BankMaster
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import ROLE_PAYROLL
from tests.permissions.mixins import RoleAPITestCase


class PayrollPermissionTests(RoleAPITestCase):
    def test_only_payroll_and_admin_roles_can_access_payroll_endpoints(self):
        denied = self.get("api_v1:bank-master-list", role=ROLE_MANAGER)
        self.assert_denied(denied)
        allowed = self.get("api_v1:bank-master-list", role=ROLE_PAYROLL)
        self.assert_http_status(allowed, status.HTTP_200_OK)
        names = {row["name"] for row in self.extract_results(allowed)}
        assert self.bank_master.name in names

    def test_payroll_role_can_create_bank_records(self):
        payload = {"name": "Bank B"}
        response = self.post(
            "api_v1:bank-master-list",
            role=ROLE_PAYROLL,
            payload=payload,
        )
        self.assert_http_status(response, status.HTTP_201_CREATED)
        assert BankMaster.objects.filter(name="Bank B").exists()
