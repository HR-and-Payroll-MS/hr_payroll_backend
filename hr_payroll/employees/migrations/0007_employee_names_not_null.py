from django.db import migrations


def backfill_employee_names(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    # Copy from related User when present; otherwise default to empty string.
    for emp in Employee.objects.all().select_related("user"):
        fn = emp.first_name or getattr(getattr(emp, "user", None), "first_name", "") or ""
        ln = emp.last_name or getattr(getattr(emp, "user", None), "last_name", "") or ""
        updated = False
        if emp.first_name != fn:
            emp.first_name = fn
            updated = True
        if emp.last_name != ln:
            emp.last_name = ln
            updated = True
        if updated:
            emp.save(update_fields=["first_name", "last_name"]) 


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0006_employee_contact_name_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_employee_names, migrations.RunPython.noop),
    ]
