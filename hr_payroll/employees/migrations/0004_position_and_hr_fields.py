from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0003_emp_dept_extras"),
    ]

    operations = [
        # Position model
        migrations.CreateModel(
            name="Position",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("salary_grade", models.CharField(blank=True, max_length=20, null=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="positions",
                        to="employees.department",
                    ),
                ),
            ],
            options={"ordering": ["title"]},
        ),

        # Department fields
        migrations.AddField(
            model_name="department",
            name="location",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="department",
            name="budget_code",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),

        # Employee fields
        migrations.AddField(
            model_name="employee",
            name="position",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employees",
                to="employees.position",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="gender",
            field=models.CharField(blank=True, choices=[("male", "Male"), ("female", "Female"), ("other", "Other")], max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="employment_status",
            field=models.CharField(choices=[
                ("active", "Active"),
                ("suspended", "Suspended"),
                ("resigned", "Resigned"),
                ("terminated", "Terminated"),
                ("retired", "Retired"),
            ], default="active", max_length=20),
        ),

        # Map title field to job_title column without data migration
        migrations.AlterField(
            model_name="employee",
            name="title",
            field=models.CharField(blank=True, db_column="job_title", max_length=150),
        ),
    ]
