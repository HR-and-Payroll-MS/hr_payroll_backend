from http import HTTPStatus

import pytest
from django.urls import reverse


def test_api_v1_docs_accessible_by_admin(admin_client):
    url = reverse("api-docs-v1")
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_api_v1_docs_not_accessible_by_anonymous_users(client):
    url = reverse("api-docs-v1")
    response = client.get(url)
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_api_v1_schema_generated_successfully(admin_client):
    url = reverse("api-schema-v1")
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK
