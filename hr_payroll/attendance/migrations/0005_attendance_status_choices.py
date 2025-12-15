from django.db import migrations, models


STATUS_CHOICES = [
    ("PRESENT", "Present"),
    ("ABSENT", "Absent"),
    ("PERMITTED", "Permitted"),
]


def forwards_update_status(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    Attendance.objects.filter(status="PENDING").update(status="PERMITTED")
    Attendance.objects.filter(status="APPROVED").update(status="PRESENT")


def backwards_update_status(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    Attendance.objects.filter(status="PRESENT").update(status="APPROVED")
    Attendance.objects.filter(status__in=["ABSENT", "PERMITTED"]).update(
        status="PENDING"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0004_officenetwork"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attendance",
            name="status",
            field=models.CharField(
                choices=STATUS_CHOICES,
                default="PRESENT",
                max_length=16,
            ),
        ),
        migrations.RunPython(forwards_update_status, backwards_update_status),
    ]
