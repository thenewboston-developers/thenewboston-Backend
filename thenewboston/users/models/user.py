from django.contrib.auth.models import AbstractUser

from ..managers.user import UserManager


class User(AbstractUser):
    objects = UserManager()
