from django.contrib.auth.models import BaseUserManager

from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.wallets.models.deposit_account import DepositAccount


class UserManager(BaseUserManager):

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(username, email, password, **extra_fields)

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        key_pair = generate_key_pair()
        DepositAccount.objects.create(
            account_number=key_pair.public,
            signing_key=key_pair.private,
            user=user,
        )

        return user
