from django.contrib.auth.models import AbstractUser
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
