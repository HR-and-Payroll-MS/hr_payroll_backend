from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.db.models import EmailField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Default custom user model for hr_payroll.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Full Name"), blank=True, max_length=255)
    email = EmailField(_("email address"), unique=True)
    # first_name = None   setting them None disabls them from usage.
    # last_name = None    so commenting them make them available from AbstractUser
    # but the more robust way is to add them again like h following
    first_name = CharField(_("First Name"), max_length=150, blank=True)
    last_name = CharField(_("Last Name"), max_length=150, blank=True)
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Automatically build th full name
        full_name = f"{self.first_name} {self.last_name}".strip()
        self.name = full_name
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    # Contact and locale
    phone = models.CharField(max_length=50, blank=True)
    time_zone = models.CharField(max_length=50, blank=True)

    # General personal information
    gender = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    marital_status = models.CharField(max_length=50, blank=True)
    personal_tax_id = models.CharField(max_length=100, blank=True)
    social_insurance = models.CharField(max_length=100, blank=True)

    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Profile({self.user.username})"
