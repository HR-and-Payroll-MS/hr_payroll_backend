import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from hr_payroll.users.auth_backends import UsernameOrEmailBackend

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestUsernameOrEmailBackend:
    def setup_method(self):
        self.backend = UsernameOrEmailBackend()
        self.password = "Sahm1232"  # noqa: S105  # Allow hardcoded password in test
        self.user = User.objects.create_user(
            username="test",
            email="test@gmail.com",
            password=self.password,
        )

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_authenticate_with_username(self):
        user = self.backend.authenticate(
            None,
            username="test",
            password=self.password,
        )
        assert user == self.user

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_authenticate_with_email(self):
        user = self.backend.authenticate(
            None,
            username="test@gmail.com",
            password=self.password,
        )
        assert user == self.user

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_authenticate_with_wrong_username(self):
        user = self.backend.authenticate(
            None,
            username="wronguser",
            password=self.password,
        )
        assert user is None

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_authenticate_with_wrong_email(self):
        user = self.backend.authenticate(
            None,
            username="wrong@gmail.com",
            password=self.password,
        )
        assert user is None

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_wrong_password_with_correct_username(self):
        user = self.backend.authenticate(
            None,
            username="test",
            password="wrongpass",  # noqa: S106
        )
        assert user is None

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_wrong_password_with_correct_email(self):
        user = self.backend.authenticate(
            None,
            username="test@gmail.com",
            password="wrongpass",  # noqa: S106
        )
        assert user is None

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_wrong_username_and_wrong_password(self):
        user = self.backend.authenticate(
            None,
            username="wronguser",
            password="wrongpass",  # noqa: S106
        )
        assert user is None

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "hr_payroll.users.auth_backends.UsernameOrEmailBackend",
        ],
    )
    def test_wrong_email_and_wrong_password(self):
        user = self.backend.authenticate(
            None,
            username="wrong@gmail.com",
            password="wrongpass",  # noqa: S106
        )
        assert user is None
