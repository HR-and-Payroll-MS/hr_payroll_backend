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

# This application object is used by any ASGI server configured to use this file.
django_application = get_asgi_application()

# Import websocket application here, so apps from django_application are loaded first
from config.websocket import websocket_application  # noqa: E402


async def application(scope, receive, send):
    if scope["type"] == "http":
        await django_application(scope, receive, send)
    elif scope["type"] == "websocket":
        await websocket_application(scope, receive, send)
    else:
        msg = f"Unknown scope type {scope['type']}"
        raise NotImplementedError(msg)
