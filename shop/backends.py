from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    """Allow authentication with email or username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        login_value = username or kwargs.get(user_model.USERNAME_FIELD)

        if not login_value or not password:
            return None

        try:
            user = user_model.objects.get(Q(email__iexact=login_value) | Q(username__iexact=login_value))
        except user_model.DoesNotExist:
            return None
        except user_model.MultipleObjectsReturned:
            # Fall back to a deterministic user when duplicate emails exist.
            user = user_model.objects.filter(email__iexact=login_value).order_by("id").first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
