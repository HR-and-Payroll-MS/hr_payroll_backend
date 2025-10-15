from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0005_merge_20251013_1725"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="first_name",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="last_name",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True),
        ),
    ]
