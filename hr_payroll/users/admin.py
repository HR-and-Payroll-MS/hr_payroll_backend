import string

from allauth.account.decorators import secure_admin_login
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from hr_payroll.employees.models import Employee

from .forms import UserAdminChangeForm
from .models import User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


def _email_domain() -> str:
    return getattr(settings, "GENERATED_EMAIL_DOMAIN", "hrpayroll.com")


def _generate_username(first: str, last: str) -> str:
    base = (f"{first}.{last}" or "user").lower().replace(" ", "")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {".", "-", "_"})
    while True:
        salt = get_random_string(
            4, allowed_chars=string.ascii_lowercase + string.digits
        )
        candidate = f"{base}-{salt}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


def _generate_password() -> str:
    charset = string.ascii_letters + string.digits + "!@#$%^&*()"
    return get_random_string(12, allowed_chars=charset)


class AdminUserCreateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "groups",
        ]

    def save(self, commit=True):  # noqa: FBT002
        user = super().save(commit=False)
        first = (user.first_name or "").strip() or "User"
        last = (user.last_name or "").strip() or "User"
        user.username = _generate_username(first, last)
        user.email = f"{user.username}@{_email_domain()}"
        raw_password = _generate_password()
        user.set_password(raw_password)
        user.name = f"{user.first_name} {user.last_name}".strip()
        if commit:
            user.save()
            # Persist generated password for messaging
            self.generated_password = raw_password
        return user


class EmployeeInline(admin.StackedInline):
    model = Employee
    extra = 1
    max_num = 1
    can_delete = False
    verbose_name_plural = "Employee profile"
    exclude = ["line_manager"]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.min_num = 1
        formset.validate_min = True
        return formset


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = AdminUserCreateForm
    inlines = [EmployeeInline]

    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                )
            },
        ),
    )

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email", "name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    list_display = ["id", "username", "name", "is_superuser", "is_staff"]
    search_fields = ["name", "email", "username"]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Surface generated password once on create
        generated = getattr(form, "generated_password", None)
        if generated:
            self.message_user(
                request,
                f"User created with auto-generated password: {generated}",
                level=messages.INFO,
            )
