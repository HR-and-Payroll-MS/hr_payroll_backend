from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0012_rename_date_of_birth_employee_last_working_date_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="EmployeeDocument"),
        migrations.DeleteModel(name="Contract"),
        migrations.DeleteModel(name="JobHistory"),
        migrations.DeleteModel(name="Employee"),
        migrations.DeleteModel(name="Department"),
    ]
