import logging

from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.dispatch import receiver

from hr_payroll.notifications.models import Notification

from .models import LeaveRequest

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=LeaveRequest)
def store_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            orig = LeaveRequest.objects.get(pk=instance.pk)
            instance._old_status = orig.status  # noqa: SLF001
        except LeaveRequest.DoesNotExist:
            instance._old_status = None  # noqa: SLF001
    else:
        instance._old_status = None  # noqa: SLF001


@receiver(post_save, sender=LeaveRequest)
def leave_request_notifications(sender, instance, created, **kwargs):
    if created:
        # Notify approver
        approver = instance.assigned_approver
        if not approver and instance.employee.line_manager:
            approver = instance.employee.line_manager

        if approver:
            logger.warning(
                "DEBUG: Found approver: %s (User ID: %s)", approver, approver.user.id
            )
            Notification.objects.create(
                recipient=approver.user,
                title="New Leave Request",
                message=(
                    f"{instance.employee} requested leave: "
                    f"{instance.policy.name} ({instance.duration} days/hours)"
                ),
                notification_type=Notification.Type.LEAVE_REQUEST,
                related_link=f"/leaves/{instance.id}/",
            )
        else:
            logger.warning("DEBUG: No approver found for leave request")
    # Check status change
    elif hasattr(instance, "_old_status") and instance._old_status != instance.status:  # noqa: SLF001
        if instance.status in [
            LeaveRequest.Status.APPROVED,
            LeaveRequest.Status.REJECTED,
        ]:
            Notification.objects.create(
                recipient=instance.employee.user,
                title=f"Leave Request {instance.status}",
                message=f"Your leave request has been {instance.status.lower()}.",
                notification_type=Notification.Type.APPROVAL
                if instance.status == LeaveRequest.Status.APPROVED
                else Notification.Type.REJECTION,
                related_link=f"/leaves/{instance.id}/",
            )
