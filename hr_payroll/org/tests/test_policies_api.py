import pytest
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIClient

from hr_payroll.org.models import OrganizationPolicy
from hr_payroll.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_org_policies_get_requires_auth():
    client = APIClient()
    res = client.get("/api/v1/orgs/1/policies/")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_org_policies_get_returns_defaults(user):
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.get("/api/v1/orgs/1/policies/")
    assert res.status_code == status.HTTP_200_OK

    body = res.json()
    assert "general" in body
    assert "overtimePolicy" in body
    assert body["overtimePolicy"]["overtimeRate"] == 1.5
    assert body["overtimePolicy"]["weekendRate"] == 2
    assert body["overtimePolicy"]["holidayRate"] == 2


@pytest.mark.django_db
def test_org_policies_put_forbidden_for_regular_employee(user):
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.put(
        "/api/v1/orgs/1/policies/",
        {"general": {"companyName": "Acme"}},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_org_policies_put_section_manager_updates_and_merges_defaults():
    manager = UserFactory()
    group, _ = Group.objects.get_or_create(name="Manager")
    manager.groups.add(group)

    client = APIClient()
    client.force_authenticate(user=manager)

    res = client.put(
        "/api/v1/orgs/1/policies/overtimePolicy/",
        {"overtimePolicy": {"weekendRate": 2.5}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    body = res.json()
    assert body["overtimePolicy"]["weekendRate"] == 2.5
    # Missing keys should remain present from defaults via deep merge.
    assert body["overtimePolicy"]["overtimeRate"] == 1.5
    assert body["overtimePolicy"]["holidayRate"] == 2

    row = OrganizationPolicy.objects.get(org_id=1)
    assert row.document["overtimePolicy"]["weekendRate"] == 2.5


@pytest.mark.django_db
def test_org_policies_put_full_document_manager_updates_and_merges_defaults():
    manager = UserFactory()
    group, _ = Group.objects.get_or_create(name="Manager")
    manager.groups.add(group)

    client = APIClient()
    client.force_authenticate(user=manager)

    res = client.put(
        "/api/v1/orgs/1/policies/",
        {"general": {"companyName": "Acme"}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    body = res.json()
    assert body["general"]["companyName"] == "Acme"
    # Other default keys should still exist.
    assert "effectiveDate" in body["general"]
