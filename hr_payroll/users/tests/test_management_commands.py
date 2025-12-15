from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command


def test_setup_rbac_creates_default_groups(db):
    expected_groups = ["Admin", "Manager", "Payroll", "Line Manager", "Employee"]
    Group.objects.filter(name__in=expected_groups).delete()

    call_command("setup_rbac")

    for name in expected_groups:
        assert Group.objects.filter(name=name).exists()

    user_model = get_user_model()
    model_codename = user_model._meta.model_name  # noqa: SLF001

    admin = Group.objects.get(name="Admin")
    manager = Group.objects.get(name="Manager")
    payroll = Group.objects.get(name="Payroll")
    line_manager = Group.objects.get(name="Line Manager")
    employee = Group.objects.get(name="Employee")

    assert admin.permissions.filter(codename__icontains=model_codename).exists()
    assert manager.permissions.filter(
        codename__in=[f"view_{model_codename}", f"change_{model_codename}"]
    ).exists()
    assert payroll.permissions.filter(codename__icontains="payroll").exists()
    assert line_manager.permissions.filter(codename__icontains="attendance").exists()
    assert employee.permissions.filter(codename__startswith="view_").exists()
