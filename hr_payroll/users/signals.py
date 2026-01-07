from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=get_user_model())
def add_default_employee_group(sender, instance, created, **kwargs):
    """Assign every newly created user to the least-privileged 'Employee' group.

    This ensures new signups have a default role without requiring manual admin action.
    Safe to call repeatedly; the group is created if missing.
    """

    if not created:
        return

    group, _ = Group.objects.get_or_create(name="Employee")
    # Add user to default group (idempotent)
    instance.groups.add(group)


logger = logging.getLogger(__name__)
ELEVATED_GROUPS = {"Admin", "Manager", "Payroll", "Line Manager"}


@receiver(m2m_changed, sender=get_user_model().groups.through)
def prevent_elevated_without_employee(sender, instance, action, pk_set, **kwargs):
    """Block adding elevated roles to users without an employee profile (unless staff/superuser).

    Allows the default "Employee" group for onboarding flow. Logs and silently drops
    disallowed groups instead of raising to avoid breaking admin UX.
    """

    if action != "pre_add" or not pk_set:
        return

    if getattr(instance, "is_superuser", False) or getattr(instance, "is_staff", False):
        return

    if getattr(instance, "employee", None):
        return

    blocked_ids = set()
    for gid in pk_set:
        try:
            g = Group.objects.get(pk=gid)
        except Group.DoesNotExist:  # pragma: no cover - defensive
            continue
        if g.name in ELEVATED_GROUPS:
            blocked_ids.add(gid)

    if not blocked_ids:
        return

    pk_set.difference_update(blocked_ids)
    logger.warning(
        "Blocked elevated group assignment without employee profile",
        extra={
            "user_id": getattr(instance, "id", None),
            "blocked_group_ids": list(blocked_ids),
        },
    )
