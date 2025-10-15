from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0002_alter_employeedocument_file"),
    ]

    operations = [
        # Department additions
        migrations.AddField(
            model_name="department",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="department",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="department",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="department",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_departments",
                to="employees.employee",
            ),
        ),
        migrations.AlterField(
            model_name="department",
            name="name",
            field=models.CharField(db_index=True, max_length=150, unique=True),
        ),

        # Employee additions
        migrations.AddField(
            model_name="employee",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="supervisor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subordinates",
                to="employees.employee",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="national_id",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="phone",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="address",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="employee",
            name="user",
            field=models.OneToOneField(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="users.user",
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="department",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employees",
                to="employees.department",
            ),
        ),

        # EmployeeDocument additions
        migrations.AddField(
            model_name="employeedocument",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="employeedocument",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
