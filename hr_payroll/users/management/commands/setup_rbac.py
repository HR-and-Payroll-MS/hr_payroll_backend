from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    help = _("Create default RBAC groups and permissions")

    def handle(self, *args, **options):
        user_model = get_user_model()
        user_ct = ContentType.objects.get_for_model(user_model)

        # Basic permissions for User model as a placeholder for Iteration 0
        user_perms = Permission.objects.filter(content_type=user_ct)
        # Django exposes model_name on _meta; acceptable for internal utilities
        model_codename = user_model._meta.model_name  # noqa: SLF001

        roles = {
            "Admin": {"permissions": list(user_perms)},
            "Manager": {
                "permissions": list(
                    user_perms.filter(
                        codename__in=[
                            f"view_{model_codename}",
                            f"change_{model_codename}",
                        ],
                    ),
                ),
            },
            "Employee": {
                "permissions": list(
                    user_perms.filter(
                        codename__in=[f"view_{model_codename}"],
                    ),
                ),
            },
        }

        for role_name, conf in roles.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            perms = conf.get("permissions", [])
            if perms:
                group.permissions.set(perms)  # type: ignore[arg-type]
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured group '{role_name}' with permissions ({len(perms)})",
                )
            )

        self.stdout.write(self.style.SUCCESS("RBAC setup complete"))
