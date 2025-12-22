"""
ASGI config for hr_payroll project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/asgi/

"""

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

# This allows easy placement of apps within the interior
# hr_payroll directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "hr_payroll"))

# If DJANGO_SETTINGS_MODULE is unset, select a sensible default based on BUILD_ENV
# Default to local settings for the local dev image, production otherwise.
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    build_env = os.environ.get("BUILD_ENV", "production").lower()
    default_settings = (
        "config.settings.local"
        if build_env == "local"
        else "config.settings.production"
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)

django_application = get_asgi_application()

from socketio import ASGIApp  # noqa: E402

from hr_payroll.realtime.socketio import sio  # noqa: E402

# Socket.IO must sit above the ProtocolTypeRouter because it uses BOTH:
# - HTTP long-polling (Engine.IO)
# - WebSocket upgrades
# Mount it at `/ws/notifications/` to match the frontend `path`.
application = ASGIApp(
    sio,
    other_asgi_app=django_application,
    socketio_path="ws/notifications",
)
