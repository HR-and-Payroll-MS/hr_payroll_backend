import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from datetime import date

from hr_payroll.payroll.models import TaxCode
from hr_payroll.payroll.models import TaxCodeVersion


def seed():
    code, created = TaxCode.objects.get_or_create(
        code="IT-001", defaults={"name": "Standard Income Tax", "is_active": True}
    )
    if created:
        pass
    else:
        pass

    # Ensure a version exists for 2025
    if not code.versions.exists():
        TaxCodeVersion.objects.create(
            tax_code=code,
            effective_from=date(2020, 1, 1),
            version_number=1,
            is_active=True,
            # Simple flat rate for demo
            rules={"rate": 15.0, "type": "flat"},
        )
    else:
        pass


if __name__ == "__main__":
    seed()
