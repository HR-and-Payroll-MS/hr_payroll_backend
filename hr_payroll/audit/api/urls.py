from django.urls import path

from hr_payroll.audit.api.views import RecentAuditView

app_name = "audit"

urlpatterns = [
    path("recent/", RecentAuditView.as_view(), name="recent"),
]
