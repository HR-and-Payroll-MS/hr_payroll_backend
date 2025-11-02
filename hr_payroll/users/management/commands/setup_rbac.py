from contextlib import suppress

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

        (
            models,
            department_model,
            emp_model,
            employee_document_model,
            job_history_model,
            contract_model,
            has_employee_document,
        ) = self._collect_models(user_model)

        context = {
            "department_model": department_model,
            "emp_model": emp_model,
            "employee_document_model": employee_document_model,
            "job_history_model": job_history_model,
            "contract_model": contract_model,
            "has_employee_document": has_employee_document,
        }

        roles = self._build_roles(models, context)

        self._apply_roles(roles)

        self.stdout.write(self.style.SUCCESS("RBAC setup complete"))

    def _collect_models(self, user_model):
        """Collect optional models from other apps if available.

        Returns a tuple: (models, department_model, emp_model,
        employee_document_model, job_history_model, contract_model,
        has_employee_document)
        """
        models = [user_model]
        department_model = None
        emp_model = None
        employee_document_model = None
        job_history_model = None
        contract_model = None
        has_employee_document = False

        with suppress(Exception):
            # Imported dynamically to avoid hard dependency on org app
            from hr_payroll.org.models import (  # noqa: PLC0415
                Department as DepartmentModel,
            )

            department_model = DepartmentModel
            models.append(DepartmentModel)

        with suppress(Exception):
            # Imported dynamically to avoid hard dependency on employees app
            from hr_payroll.employees.models import (  # noqa: PLC0415
                Contract as ContractModel,
            )
            from hr_payroll.employees.models import (  # noqa: PLC0415
                Employee as EmpModel,
            )
            from hr_payroll.employees.models import (  # noqa: PLC0415
                EmployeeDocument as EmployeeDocumentModel,
            )
            from hr_payroll.employees.models import (  # noqa: PLC0415
                JobHistory as JobHistoryModel,
            )

            emp_model = EmpModel
            employee_document_model = EmployeeDocumentModel
            job_history_model = JobHistoryModel
            contract_model = ContractModel
            models.extend(
                [
                    EmpModel,
                    EmployeeDocumentModel,
                    JobHistoryModel,
                    ContractModel,
                ]
            )
            has_employee_document = True

        return (
            models,
            department_model,
            emp_model,
            employee_document_model,
            job_history_model,
            contract_model,
            has_employee_document,
        )

    def _build_roles(self, models, context):
        """Build a mapping of roles to permission querysets."""
        admin_perms: list[Permission] = []
        manager_perms: list[Permission] = []
        employee_perms: list[Permission] = []
        line_manager_perms: list[Permission] = []

        department_model = context.get("department_model")
        emp_model = context.get("emp_model")
        employee_document_model = context.get("employee_document_model")
        job_history_model = context.get("job_history_model")
        contract_model = context.get("contract_model")
        has_employee_document = context.get("has_employee_document")

        for model in models:
            ct = ContentType.objects.get_for_model(model)
            model_perms = Permission.objects.filter(content_type=ct)
            admin_perms.extend(model_perms)

            model_name = model._meta.model_name  # noqa: SLF001
            manager_perms.extend(
                model_perms.filter(
                    codename__in=[f"view_{model_name}", f"change_{model_name}"],
                ),
            )

            employee_perms.extend(model_perms.filter(codename=f"view_{model_name}"))

            if (
                has_employee_document
                and employee_document_model is not None
                and model is employee_document_model
            ):
                employee_perms.extend(model_perms.filter(codename=f"add_{model_name}"))

            if emp_model is not None and model is emp_model:
                line_manager_perms.extend(
                    model_perms.filter(
                        codename__in=[f"view_{model_name}", f"change_{model_name}"],
                    )
                )
            elif department_model is not None and model is department_model:
                line_manager_perms.extend(
                    model_perms.filter(codename__in=[f"view_{model_name}"])
                )
            elif (job_history_model is not None and model is job_history_model) or (
                contract_model is not None and model is contract_model
            ):
                line_manager_perms.extend(
                    model_perms.filter(
                        codename__in=[
                            f"view_{model_name}",
                            f"add_{model_name}",
                            f"change_{model_name}",
                        ]
                    )
                )

        return {
            "Admin": {"permissions": admin_perms},
            "Manager": {"permissions": manager_perms},
            "Employee": {"permissions": employee_perms},
            "Line Manager": {"permissions": line_manager_perms},
        }

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
