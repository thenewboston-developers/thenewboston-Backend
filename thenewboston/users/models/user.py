from django.contrib.auth.models import AbstractUser
from django.db import models

from thenewboston.general.models import SocialMediaMixin
from thenewboston.wallets.models import Wallet

from ..managers.user import UserManager


class User(AbstractUser, SocialMediaMixin):
    avatar = models.ImageField(upload_to='images/', blank=True)
    banner = models.ImageField(upload_to='banners/', blank=True)
    bio = models.CharField(max_length=160, blank=True)

    objects = UserManager()

    def get_reward_wallet_for_currency(self, currency_id, with_for_update=True):
        query = Wallet.objects
        if with_for_update:
            query = query.select_for_update()

        wallet, _ = query.get_or_create(currency_id=currency_id, owner=self)
        return wallet
