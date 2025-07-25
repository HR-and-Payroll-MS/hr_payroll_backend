from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        usermodel = get_user_model()
        try:
            user = usermodel.objects.get(email__iexact=username)
        except usermodel.DoesNotExist:
            try:
                user = usermodel.objects.get(username__iexact=username)
            except usermodel.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
