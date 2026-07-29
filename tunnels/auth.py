from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .forms import normalize_account_email


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get("email")
        if not email or password is None:
            return None
        normalized_email = normalize_account_email(email)
        user_model = get_user_model()
        try:
            user = user_model._default_manager.get(email__iexact=normalized_email)
        except (user_model.DoesNotExist, user_model.MultipleObjectsReturned):
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
