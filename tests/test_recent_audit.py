from __future__ import annotations

from django.utils import timezone

from hr_payroll.audit.models import AuditLog
from tests.permissions.mixins import ROLE_EMPLOYEE
from tests.permissions.mixins import ROLE_LINE_MANAGER
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import RoleAPITestCase


class TestRecentAuditEndpoint(RoleAPITestCase):
    def test_recent_audit_requires_elevated_role(self):
        denied = self.get("api_v1:audit:recent", role=ROLE_EMPLOYEE)
        self.assert_http_status(denied, 403)

        allowed = self.get("api_v1:audit:recent", role=ROLE_MANAGER)
        self.assert_http_status(allowed, 200)

    def test_recent_audit_returns_latest_5(self):
        # Create 6 logs with deterministic timestamps so ordering is stable.
        base = timezone.now()
        created = []
        for i in range(6):
            row = AuditLog.objects.create(action=f"test_action_{i}", message=str(i))
            created.append(row)
        for i, row in enumerate(created):
            AuditLog.objects.filter(pk=row.pk).update(
                created_at=base + timezone.timedelta(seconds=i)
            )

        res = self.get("api_v1:audit:recent", role=ROLE_LINE_MANAGER)
        self.assert_http_status(res, 200)
        assert "results" in res.data
        assert len(res.data["results"]) == 5

        # Since ordering is newest-first, we expect actions 5..1
        actions = [r["action"] for r in res.data["results"]]
        assert actions == [
            "test_action_5",
            "test_action_4",
            "test_action_3",
            "test_action_2",
            "test_action_1",
        ]
