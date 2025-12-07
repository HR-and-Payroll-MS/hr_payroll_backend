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

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter  # noqa: E402
from channels.routing import URLRouter  # noqa: E402

import hr_payroll.notifications.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_application,
        "websocket": AuthMiddlewareStack(
            URLRouter(hr_payroll.notifications.routing.websocket_urlpatterns)
        ),
    }
)
