from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command


def test_setup_rbac_creates_default_groups(db):
    # Ensure groups do not exist
    Group.objects.filter(name__in=["Admin", "Manager", "Employee"]).delete()

    call_command("setup_rbac")

    assert Group.objects.filter(name="Admin").exists()
    assert Group.objects.filter(name="Manager").exists()
    assert Group.objects.filter(name="Employee").exists()

    # Sanity: admin should have some permissions, employee at least view
    user_model = get_user_model()
    admin = Group.objects.get(name="Admin")
    manager = Group.objects.get(name="Manager")
    employee = Group.objects.get(name="Employee")

    model_codename = user_model._meta.model_name  # noqa: SLF001
    assert admin.permissions.filter(codename__icontains=model_codename).exists()
    assert (
        manager.permissions.filter(
            codename__in=[
                f"view_{model_codename}",
                f"change_{model_codename}",
            ],
        ).count()
        >= 1
    )
    assert (
        employee.permissions.filter(
            codename__in=[f"view_{model_codename}"],
        ).count()
        >= 1
    )
