from django.db.models.signals import post_save
from django.dispatch import receiver

from hr_payroll.attendance.api.serializers import AttendanceRecordSerializer
from hr_payroll.attendance.models import AttendanceRecord
from hr_payroll.realtime.events import EVENT_ATTENDANCE_UPDATE
from hr_payroll.realtime.socketio import emit_event_to_group


@receiver(post_save, sender=AttendanceRecord)
def broadcast_attendance_update(sender, instance: AttendanceRecord, **kwargs):
    """Notify HR Managers of attendance changes."""
    # Serialize basic data or just the ID/Action to trigger a refresh
    # Sending full data allows for "live table update" without refetch
    payload = AttendanceRecordSerializer(instance).data

    # 1. Notify all HR Managers (who view the global dashboard)
    emit_event_to_group("HR Manager", EVENT_ATTENDANCE_UPDATE, payload)

    # 2. Notify Department ID (if we implement department-level dashboards)
    if instance.employee.department_id:
        pass
