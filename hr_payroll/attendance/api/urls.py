from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter

from hr_payroll.attendance.api import views

router = DefaultRouter()
router.register(
    "departments", views.DepartmentAttendanceViewSet, basename="attendance-departments"
)
router.register(
    "records", views.AttendanceRecordAdminViewSet, basename="attendance-records"
)

urlpatterns = [
    # HR/staff attendance management under /attendances/
    path("attendances/", include(router.urls)),
    path(
        "attendances/<int:pk>/",
        views.AttendanceRecordAdminViewSet.as_view({"patch": "partial_update"}),
        name="attendance-records-direct",
    ),
    # Employee-scoped endpoints (network/today/clock in/out)
    path(
        "employees/<int:employee_id>/attendances/network-status/",
        views.NetworkStatusView.as_view(),
        name="attendance-network-status",
    ),
    path(
        "employees/<int:employee_id>/attendances/today/",
        views.TodayAttendanceView.as_view(),
        name="attendance-today",
    ),
    path(
        "employees/<int:employee_id>/attendances/clock-in/",
        views.ClockInView.as_view(),
        name="attendance-clock-in",
    ),
    path(
        "employees/<int:employee_id>/attendances/clock-out/",
        views.ClockOutView.as_view(),
        name="attendance-clock-out",
    ),
    path(
        "employees/<int:employee_id>/attendances/<int:record_id>/",
        views.AttendanceCorrectionView.as_view(),
        name="attendance-correction",
    ),
]
