from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr_payroll.messaging"
    verbose_name = _("Messaging")

    def ready(self):
        import hr_payroll.messaging.signals  # noqa: F401
