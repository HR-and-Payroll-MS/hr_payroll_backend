from django.apps import AppConfig


class OrgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr_payroll.org"
    verbose_name = "Organization"
