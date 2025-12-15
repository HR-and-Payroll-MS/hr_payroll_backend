from collections import defaultdict
from contextlib import suppress

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

FULL_ACTIONS = ("add", "change", "delete", "view")
MANAGE_ACTIONS = ("add", "change", "view")
APPROVE_ACTIONS = ("change", "view")
READ_ACTIONS = ("view",)
ROLE_EMPLOYEE = "Employee"

ROLE_APP_ACTIONS = {
    "Manager": {
        "attendance": FULL_ACTIONS,
        "employees": FULL_ACTIONS,
        "leaves": FULL_ACTIONS,
        "org": FULL_ACTIONS,
        "notifications": MANAGE_ACTIONS,
        "users": MANAGE_ACTIONS,
    },
    "Payroll": {
        "payroll": FULL_ACTIONS,
        "employees": READ_ACTIONS,
        "org": READ_ACTIONS,
        "notifications": READ_ACTIONS,
    },
    "Line Manager": {
        "attendance": APPROVE_ACTIONS,
        "employees": APPROVE_ACTIONS,
        "leaves": APPROVE_ACTIONS,
        "org": READ_ACTIONS,
        "notifications": READ_ACTIONS,
    },
    "Employee": {
        "attendance": READ_ACTIONS,
        "employees": READ_ACTIONS,
        "leaves": READ_ACTIONS,
        "notifications": READ_ACTIONS,
        "payroll": READ_ACTIONS,
    },
}

ROLE_MODEL_ACTIONS = {
    ("employees", "employeedocument"): {
        "Employee": ("add", "view"),
        "Line Manager": ("add", "change", "view"),
    },
    ("employees", "employee"): {
        "Payroll": ("view",),
    },
    ("leaves", "leaverequest"): {
        "Employee": ("add", "change", "view"),
        "Line Manager": ("change", "view"),
    },
}


class Command(BaseCommand):
    help = _("Create default RBAC groups and permissions")

    def handle(self, *args, **options):
        user_model = get_user_model()
        models = self._collect_models(user_model)
        roles = self._build_roles(models, user_model)
        self._apply_roles(roles)
        self.stdout.write(self.style.SUCCESS("RBAC setup complete"))

    def _collect_models(self, user_model):
        """Gather models from target apps to drive permission creation."""

        seen_models: set[type] = set()
        collected: list[type] = []

        def add_model(model):
            if model not in seen_models:
                seen_models.add(model)
                collected.append(model)

        add_model(user_model)

        for label in sorted(self._target_app_labels()):
            for model in self._collect_app_models(label):
                add_model(model)

        return collected

    def _target_app_labels(self):
        labels = set()
        for rules in ROLE_APP_ACTIONS.values():
            labels.update(rules.keys())
        for app_label, _unused in ROLE_MODEL_ACTIONS:
            labels.add(app_label)
        return labels

    def _collect_app_models(self, label):
        with suppress(LookupError):
            app_config = apps.get_app_config(label)
            return list(app_config.get_models())
        return []

    def _build_roles(self, models, user_model):
        """Construct per-role permission querysets."""

        admin_perm_ids: set[int] = set()
        role_perm_ids: dict[str, set[int]] = defaultdict(set)

        for model in models:
            ct = ContentType.objects.get_for_model(model)
            model_perms = list(Permission.objects.filter(content_type=ct))
            if not model_perms:
                continue

            admin_perm_ids.update(perm.pk for perm in model_perms)

            model_name = model._meta.model_name  # noqa: SLF001
            app_label = model._meta.app_label  # noqa: SLF001
            perms_by_codename = {perm.codename: perm for perm in model_perms}

            for role_name, app_rules in ROLE_APP_ACTIONS.items():
                actions = app_rules.get(app_label)
                if actions:
                    self._add_actions(
                        role_perm_ids[role_name], perms_by_codename, model_name, actions
                    )

            for (
                rule_app_label,
                rule_model_name,
            ), role_actions in ROLE_MODEL_ACTIONS.items():
                if (rule_app_label, rule_model_name) != (app_label, model_name):
                    continue
                for role_name, actions in role_actions.items():
                    self._add_actions(
                        role_perm_ids[role_name], perms_by_codename, model_name, actions
                    )

        # Guarantee employees retain at least read access to their own user records.
        employee_view_perm = Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(user_model),
            codename=f"view_{user_model._meta.model_name}",  # noqa: SLF001
        ).first()
        if employee_view_perm:
            role_perm_ids[ROLE_EMPLOYEE].add(employee_view_perm.pk)

        roles = {
            "Admin": {"permissions": Permission.objects.filter(pk__in=admin_perm_ids)}
        }

        for role_name, perm_ids in role_perm_ids.items():
            roles[role_name] = {
                "permissions": Permission.objects.filter(pk__in=perm_ids)
            }

        return roles

    def _add_actions(self, bucket, perms_by_codename, model_name, actions):
        for action in actions:
            codename = f"{action}_{model_name}"
            perm = perms_by_codename.get(codename)
            if perm:
                bucket.add(perm.pk)

    def _apply_roles(self, roles):
        """Create/update groups and assign permissions."""
        for role_name, conf in roles.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            perms = conf.get("permissions", [])
            if perms:
                perm_ids = {p.pk for p in perms}
                unique_perms = Permission.objects.filter(pk__in=perm_ids)
                group.permissions.set(list(unique_perms))  # type: ignore[arg-type]
                count = unique_perms.count()
            else:
                group.permissions.clear()
                count = 0
            msg = f"Ensured group '{role_name}' with permissions ({count})"
            self.stdout.write(self.style.SUCCESS(msg))
