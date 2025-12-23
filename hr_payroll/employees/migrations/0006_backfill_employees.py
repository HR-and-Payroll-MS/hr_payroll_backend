from django.conf import settings
from django.db import migrations


def backfill_employees(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL.split(".")[0], settings.AUTH_USER_MODEL.split(".")[1])
    Employee = apps.get_model("employees", "Employee")

    existing_user_ids = set(Employee.objects.values_list("user_id", flat=True))
    to_create = []
    for u in User.objects.all().iterator():
        if u.id in existing_user_ids:
            continue
        base = u.username or u.email or f"user-{u.pk}"
        emp_id_candidate = base.replace(" ", "-")[:40] or f"emp-{u.pk}"
        emp_id = emp_id_candidate
        suffix = 0
        while Employee.objects.filter(employee_id=emp_id).exists():
            suffix += 1
            emp_id = f"{emp_id_candidate}-{suffix}"
        to_create.append(Employee(user_id=u.id, employee_id=emp_id))

    if to_create:
        Employee.objects.bulk_create(to_create, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0005_alter_employee_fingerprint_token"),
        ("users", "0002_add_payroll_group"),
    ]

    operations = [
        migrations.RunPython(backfill_employees, migrations.RunPython.noop),
    ]
