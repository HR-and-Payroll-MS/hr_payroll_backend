import decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0001_initial"),
        ("employees", "0005_alter_employee_fingerprint_token"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayslipDocument",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("month", models.CharField(blank=True, help_text="Payroll month in YYYY-MM format (from preview/upload)", max_length=7)),
                (
                    "file",
                    models.FileField(upload_to="payslips/"),
                ),
                (
                    "gross",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        help_text="Gross amount from the generated slip",
                        max_digits=12,
                    ),
                ),
                (
                    "net",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        help_text="Net amount from the generated slip",
                        max_digits=12,
                    ),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "cycle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payslip_documents",
                        to="payroll.paycycle",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payslip_documents",
                        to="employees.employee",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_payslip_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at"],
                "verbose_name": "Payslip Document",
                "verbose_name_plural": "Payslip Documents",
            },
        ),
    ]
