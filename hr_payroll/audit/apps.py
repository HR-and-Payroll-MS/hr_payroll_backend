import importlib

from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr_payroll.audit"

    def ready(self) -> None:  # pragma: no cover
        importlib.import_module("hr_payroll.audit.signals")
        return super().ready()
