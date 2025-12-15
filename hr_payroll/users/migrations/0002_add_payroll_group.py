from django.db import migrations


def create_payroll_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    payroll_group, _ = Group.objects.get_or_create(name="Payroll")
    payroll_perms = Permission.objects.filter(content_type__app_label="payroll")
    payroll_group.permissions.add(*payroll_perms)


def remove_payroll_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Payroll").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_payroll_group, remove_payroll_group),
    ]
