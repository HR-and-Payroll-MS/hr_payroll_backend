"""
WSGI config for hr_payroll project.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runfcgi`` commands discover
this application via the ``WSGI_APPLICATION`` setting.

Usually you will have the standard Django WSGI application here, but it also
might make sense to replace the whole Django WSGI application with a custom one
that later delegates to the Django one. For example, you could introduce WSGI
middleware here, or combine a Django application with an application of another
framework.

"""

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# This allows easy placement of apps within the interior
# hr_payroll directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "hr_payroll"))
# If DJANGO_SETTINGS_MODULE is unset, select a sensible default based on BUILD_ENV
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    build_env = os.environ.get("BUILD_ENV", "production").lower()
    default_settings = (
        "config.settings.local"
        if build_env == "local"
        else "config.settings.production"
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.
application = get_wsgi_application()
