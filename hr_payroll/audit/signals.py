from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .utils import log_action


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    ip = request.META.get("REMOTE_ADDR", "-") if request else "-"
    ua = request.META.get("HTTP_USER_AGENT", "-") if request else "-"
    log_action("login", actor=user, message=f"ip={ip} ua={ua}")
