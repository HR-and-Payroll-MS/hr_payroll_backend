import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def obtain_tokens(client, username: str, password: str) -> tuple[str, str]:
    r = client.post(
        "/api/v1/auth/jwt/create/",
        {"username": username, "password": password},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK, r.content
    return r.data["access"], r.data["refresh"]


def test_jwt_verify_endpoint():
    user_model = get_user_model()
    user_model.objects.create_user(
        username="verifyuser",
        email="verify@example.com",
        password="VerifyPass!123",  # noqa: S106
    )
    client = APIClient()
    access, _ = obtain_tokens(client, "verifyuser", "VerifyPass!123")

    # Verify should succeed
    r = client.post(
        "/api/v1/auth/jwt/verify/",
        {"token": access},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK

    # Corrupt token should fail
    bad = access[:-2] + "ab"
    r = client.post(
        "/api/v1/auth/jwt/verify/",
        {"token": bad},
        format="json",
    )
    assert r.status_code == status.HTTP_401_UNAUTHORIZED
