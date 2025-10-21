from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0008_alter_department_budget_code_and_more"),
    ]

    operations = [
        # Remove the global unique constraint by altering the field
        migrations.AlterField(
            model_name="employee",
            name="national_id",
            field=models.CharField(max_length=50, blank=True),
        ),
        # Add a conditional unique constraint: unique only when non-blank
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                fields=["national_id"],
                name="uniq_employee_national_id_nonblank",
                condition=~Q(national_id=""),
            ),
        ),
    ]
