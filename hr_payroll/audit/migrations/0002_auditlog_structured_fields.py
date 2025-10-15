from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="model_name",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="record_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="before",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="after",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="ip_address",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
