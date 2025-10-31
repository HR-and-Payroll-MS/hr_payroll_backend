import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase


@pytest.mark.skipif(
    not getattr(settings, "DJOSER_ENABLED", False),
    reason="Djoser endpoints disabled in settings",
)
class TestDjoserJWTFlow(APITestCase):
    def test_register_login_refresh_and_me(self):
        # 0) Prepare: create a Manager and authenticate (registration restricted)
        user_model = get_user_model()
        manager = user_model.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="ManagerPass!123",  # noqa: S106
        )
        manager.is_active = True
        manager.save()
        # Add Manager group
        mgr_group, _ = Group.objects.get_or_create(name="Manager")
        manager.groups.add(mgr_group)
        self.client.force_authenticate(user=manager)

        # 1) Register (as Manager)
        payload = {
            "username": "testseud",
            "email": "testseud@gmail.com",
            "password": "testPassword123!",  # Allow hardcoded password in test
            "re_password": "testPassword123!",  # Allow hardcoded password in test
        }
        r = self.client.post("/api/v1/auth/users/", payload, format="json")
        assert r.status_code in (status.HTTP_201_CREATED, status.HTTP_204_NO_CONTENT)

        # User is active immediately (activation emails disabled)
        user = user_model.objects.get(username="testseud")
        assert user.is_active is True

        # 2) Login (JWT create)
        # Clear manager force-auth so JWT auth is used
        self.client.force_authenticate(user=None)
        r = self.client.post(
            "/api/v1/auth/jwt/create/",
            {
                "username": "testseud",
                "password": "testPassword123!",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        access = r.data.get("access")
        refresh = r.data.get("refresh")
        assert access is not None
        assert refresh is not None

        # 3) Refresh
        r = self.client.post(
            "/api/v1/auth/jwt/refresh/",
            {"refresh": refresh},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        new_access = r.data.get("access")
        assert new_access is not None

        # 4) Me with Bearer token
        # Ensure no lingering force-auth; use Bearer token
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        r = self.client.get("/api/v1/auth/users/me/")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["username"] == "testseud"
        assert r.data["email"] == "testseud@gmail.com"

    def test_login_with_email_value_in_username_field(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="StrongPass!234",  # noqa: S106
        )
        user.is_active = True
        user.save()

        r = self.client.post(
            "/api/v1/auth/jwt/create/",
            {
                "username": "bob@example.com",
                "password": "StrongPass!234",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        assert "access" in r.data
        assert "refresh" in r.data
