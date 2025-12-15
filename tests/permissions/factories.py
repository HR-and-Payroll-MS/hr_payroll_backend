from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from hr_payroll.employees.models import Employee

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hr_payroll.org.models import Department

User = get_user_model()


@dataclass
class RoleContext:
    user: User
    employee: Employee


def ensure_groups(names: Iterable[str]) -> None:
    for name in names:
        Group.objects.get_or_create(name=name)


def create_user_with_role(
    username: str,
    *,
    groups: Iterable[str] | None = None,
    is_staff: bool = False,
    department: Department | None = None,
    line_manager: Employee | None = None,
) -> RoleContext:
    ensure_groups(groups or [])
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",  # noqa: S106
    )
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    for group_name in groups or []:
        user.groups.add(Group.objects.get(name=group_name))
    employee = Employee.objects.create(
        user=user,
        department=department,
        line_manager=line_manager,
        is_active=True,
    )
    return RoleContext(user=user, employee=employee)
