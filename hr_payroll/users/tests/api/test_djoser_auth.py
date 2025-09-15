# ruff: noqa: S106
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from djoser.utils import encode_uid
from rest_framework import status
from rest_framework.test import APITestCase


class TestDjoserJWTFlow(APITestCase):
    def test_register_activate_login_refresh_and_me(self):
        # 1) Register
        payload = {
            "username": "testseud",
            "email": "testseud@gmail.com",
            "password": "testPassword123!",  # ruff: noqa: S106 # Allow hardcoded password in test
            "re_password": "testPassword123!",  # ruff: noqa: S106 # Allow hardcoded password in test
        }
        r = self.client.post("/api/auth/users/", payload, format="json")
        assert r.status_code in (status.HTTP_201_CREATED, status.HTTP_204_NO_CONTENT)

        # User inactive until activation
        user_model = get_user_model()
        user = user_model.objects.get(username="testseud")
        assert user.is_active is False

        # 2) Activate
        uid = encode_uid(user.pk)
        token = default_token_generator.make_token(user)
        r = self.client.post(
            "/api/auth/users/activation/",
            {"uid": uid, "token": token},
            format="json",
        )
        assert r.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        user.refresh_from_db()
        assert user.is_active is True

        # 3) Login (JWT create)
        r = self.client.post(
            "/api/auth/jwt/create/",
            {
                "username": "testseud",
                "password": "testPassword123!",
            },  # ruff: noqa: S106  # Allow hardcoded password in test
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        access = r.data.get("access")
        refresh = r.data.get("refresh")
        assert access is not None
        assert refresh is not None

        # 4) Refresh
        r = self.client.post(
            "/api/auth/jwt/refresh/",
            {"refresh": refresh},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        new_access = r.data.get("access")
        assert new_access is not None

        # 5) Me with Bearer token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        r = self.client.get("/api/auth/users/me/")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["username"] == "testseud"
        assert r.data["email"] == "testseud@gmail.com"

    def test_login_with_email_value_in_username_field(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="StrongPass!234",
        )  # ruff: noqa: S106 # Allow hardcoded password in test
        user.is_active = True
        user.save()

        r = self.client.post(
            "/api/auth/jwt/create/",
            {
                "username": "bob@example.com",
                "password": "StrongPass!234",
            },  # ruff: noqa: S106 # Allow hardcoded password in test
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        assert "access" in r.data
        assert "refresh" in r.data
