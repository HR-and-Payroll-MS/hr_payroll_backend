from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LeavesConfig(AppConfig):
    name = "hr_payroll.leaves"
    verbose_name = _("Leaves")
