from django.urls import resolve
from django.urls import reverse


def test_users_routes_available_v1_only():
    # Only versioned route should exist
    assert reverse("api_v1:user-list") == "/api/v1/users/"
    assert resolve("/api/v1/users/").view_name == "api_v1:user-list"


def test_schema_docs_available_under_v1():
    assert resolve("/api/v1/schema/").view_name == "api-schema-v1"
    assert resolve("/api/v1/docs/").view_name == "api-docs-v1"
