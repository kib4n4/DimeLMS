from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    """Authenticate using the user's email address instead of their username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        try:
            user = UserModel.objects.exclude(email__isnull=True).exclude(email="").get(
                email__iexact=username
            )
        except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
