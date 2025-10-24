import os

from celery import Celery
from celery.signals import setup_logging

# Ensure Celery uses production settings by default in deployed environments.
# Tests and local dev explicitly set DJANGO_SETTINGS_MODULE (e.g. pytest uses
# config.settings.test via --ds), so setdefault won't override those.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("hr_payroll")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")


@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig  # noqa: PLC0415

    from django.conf import settings  # noqa: PLC0415

    dictConfig(settings.LOGGING)


# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
