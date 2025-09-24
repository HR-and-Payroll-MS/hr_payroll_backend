import pytest

from hr_payroll.audit.models import AuditLog
from hr_payroll.users.models import User


@pytest.mark.django_db
def test_audit_log_create_with_actor(user: User):
    log = AuditLog.objects.create(action="test", actor=user, message="hello")
    assert log.id is not None
    assert log.actor == user
    assert str(log).startswith("[")
