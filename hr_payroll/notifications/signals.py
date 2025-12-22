from django.db.models.signals import post_save
from django.db.transaction import on_commit
from django.dispatch import receiver

from hr_payroll.realtime.events.notifications import publish_notification_created

from .models import Notification


@receiver(post_save, sender=Notification)
def send_notification_ws(sender, instance, created, **kwargs):
    if created:
        on_commit(lambda: publish_notification_created(instance))
