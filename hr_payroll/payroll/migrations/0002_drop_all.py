from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="SalaryComponent"),
        migrations.DeleteModel(name="Compensation"),
    ]
