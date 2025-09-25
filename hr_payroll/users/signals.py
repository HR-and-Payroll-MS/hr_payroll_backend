from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
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
