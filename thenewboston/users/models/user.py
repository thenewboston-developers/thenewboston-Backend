from django.contrib.auth.models import AbstractUser
from django.db import models

from thenewboston.wallets.models import Wallet

from ..managers.user import UserManager


class User(AbstractUser):
    avatar = models.ImageField(upload_to='images/', blank=True)

    objects = UserManager()

    def get_reward_wallet_for_core(self, core_id, with_for_update=True):
        query = Wallet.objects
        if with_for_update:
            query = query.select_for_update()

        wallet, _ = query.get_or_create(core_id=core_id, owner=self)
        return wallet
