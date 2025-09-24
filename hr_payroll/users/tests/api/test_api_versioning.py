from django.urls import resolve
from django.urls import reverse


def test_users_routes_available_under_v1():
    assert reverse("api:user-list") == "/api/users/"
    assert resolve("/api/users/").view_name == "api:user-list"

    # v1 alias should expose the same routes
    assert reverse("api:user-list").replace("/api/", "/api/v1/") == "/api/v1/users/"
    assert resolve("/api/v1/users/").view_name == "api:user-list"


def test_schema_docs_available_under_v1():
    assert resolve("/api/v1/schema/").view_name == "api-schema-v1"
    assert resolve("/api/v1/docs/").view_name == "api-docs-v1"
