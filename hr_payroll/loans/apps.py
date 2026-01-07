from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LoansConfig(AppConfig):
    name = "hr_payroll.loans"
    verbose_name = _("Loans")
