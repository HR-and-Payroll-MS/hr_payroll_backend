from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None,password=None,**kwargs):
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            try:
                user = UserModel.objects.get(username__iexact=username)
            except UserModel.DoesNotExist:
                return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user