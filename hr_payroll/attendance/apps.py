from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AttendanceConfig(AppConfig):
    name = "hr_payroll.attendance"
    verbose_name = _("Attendance")

    def ready(self):
        import hr_payroll.attendance.signals  # noqa: F401
