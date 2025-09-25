from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from hr_payroll.employees.models import Department
from hr_payroll.employees.models import Employee as Emp
from hr_payroll.employees.models import EmployeeDocument


class Command(BaseCommand):
    help = _("Create default RBAC groups and permissions")

    def handle(self, *args, **options):
        user_model = get_user_model()

        # Collect content types and model names for relevant models
        models = [
            user_model,
            Department,
            Emp,
            EmployeeDocument,
        ]

        admin_perms: list[Permission] = []
        manager_perms: list[Permission] = []
        employee_perms: list[Permission] = []

        for model in models:
            ct = ContentType.objects.get_for_model(model)
            model_perms = Permission.objects.filter(content_type=ct)
            # Admin: all perms for the model
            admin_perms.extend(model_perms)

            # Manager role gets view and change permissions
            model_name = model._meta.model_name  # noqa: SLF001
            manager_perms.extend(
                model_perms.filter(
                    codename__in=[f"view_{model_name}", f"change_{model_name}"],
                ),
            )

            # Employee: view for all models
            employee_perms.extend(model_perms.filter(codename=f"view_{model_name}"))

            # Special-case: allow employees to add their own documents
            if model is EmployeeDocument:
                employee_perms.extend(model_perms.filter(codename=f"add_{model_name}"))

        roles = {
            "Admin": {"permissions": admin_perms},
            "Manager": {"permissions": manager_perms},
            "Employee": {"permissions": employee_perms},
        }

        for role_name, conf in roles.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            perms = conf.get("permissions", [])
            if perms:
                # Ensure unique permissions before assignment
                perm_ids = {p.pk for p in perms}
                unique_perms = Permission.objects.filter(pk__in=perm_ids)
                group.permissions.set(list(unique_perms))  # type: ignore[arg-type]
                count = unique_perms.count()
            else:
                group.permissions.clear()
                count = 0
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured group '{role_name}' with permissions ({count})",
                ),
            )

        self.stdout.write(self.style.SUCCESS("RBAC setup complete"))
