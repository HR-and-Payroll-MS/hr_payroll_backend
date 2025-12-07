from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr_payroll.notifications"
    verbose_name = _("Notifications")

    def ready(self):
        import hr_payroll.notifications.signals  # noqa: F401, PLC0415
