from django.contrib.auth.models import BaseUserManager
from django.db import transaction

from thenewboston.general.managers import CustomQuerySet


class UserManager(BaseUserManager.from_queryset(CustomQuerySet)):  # type: ignore
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(username, email, password, **extra_fields)

    @transaction.atomic
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user
