from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from contextlib import suppress


class Command(BaseCommand):
    help = _("Create default RBAC groups and permissions")

    def handle(self, *args, **options):
        user_model = get_user_model()

        # Collect content types and model names for relevant models
        models = [user_model]
        # Try to include org/employees models if present
        has_employee_document = False
        has_employees = False
        has_org = False
        Department = None  # type: ignore
        Emp = None  # type: ignore
        EmployeeDocument = None  # type: ignore
        JobHistory = None  # type: ignore
        Contract = None  # type: ignore
        with suppress(Exception):
            from hr_payroll.org.models import Department as DepartmentModel  # type: ignore

            Department = DepartmentModel
            models.append(DepartmentModel)
            has_org = True
        with suppress(Exception):
            from hr_payroll.employees.models import (  # type: ignore
                Employee as EmpModel,
                EmployeeDocument as EmployeeDocumentModel,
                JobHistory as JobHistoryModel,
                Contract as ContractModel,
            )

            Emp = EmpModel
            EmployeeDocument = EmployeeDocumentModel
            JobHistory = JobHistoryModel
            Contract = ContractModel
            models.extend([EmpModel, EmployeeDocumentModel, JobHistoryModel, ContractModel])
            has_employees = True
            has_employee_document = True

        admin_perms: list[Permission] = []
        manager_perms: list[Permission] = []  # HR Manager
        employee_perms: list[Permission] = []
        line_manager_perms: list[Permission] = []

        for model in models:
            ct = ContentType.objects.get_for_model(model)
            model_perms = Permission.objects.filter(content_type=ct)
            # Admin: all perms for the model
            admin_perms.extend(model_perms)

            # Manager (HR) role gets view and change permissions
            model_name = model._meta.model_name  # noqa: SLF001
            manager_perms.extend(
                model_perms.filter(
                    codename__in=[f"view_{model_name}", f"change_{model_name}"],
                ),
            )

            # Employee: view for all models
            employee_perms.extend(model_perms.filter(codename=f"view_{model_name}"))

            # Special-case: allow employees to add their own documents (if model available)
            if "EmployeeDocument" in locals() and has_employee_document and model is EmployeeDocument:
                employee_perms.extend(model_perms.filter(codename=f"add_{model_name}"))

            # Line Manager: scoped management of employees and their records
            # - Always view employees/departments/job history/contracts
            # - Change employees (limited by object-level API checks)
            # - Add/change job history and contracts
            if model is Emp:
                line_manager_perms.extend(
                    model_perms.filter(
                        codename__in=[f"view_{model_name}", f"change_{model_name}"],
                    )
                )
            elif Department is not None and model is Department:
                line_manager_perms.extend(
                    model_perms.filter(codename__in=[f"view_{model_name}"])
                )
            elif JobHistory is not None and model is JobHistory:
                line_manager_perms.extend(
                    model_perms.filter(
                        codename__in=[
                            f"view_{model_name}",
                            f"add_{model_name}",
                            f"change_{model_name}",
                        ]
                    )
                )
            elif Contract is not None and model is Contract:
                line_manager_perms.extend(
                    model_perms.filter(
                        codename__in=[
                            f"view_{model_name}",
                            f"add_{model_name}",
                            f"change_{model_name}",
                        ]
                    )
                )

        roles = {
            "Admin": {"permissions": admin_perms},
            "Manager": {"permissions": manager_perms},  # HR Manager
            "Employee": {"permissions": employee_perms},
            "Line Manager": {"permissions": line_manager_perms},
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
