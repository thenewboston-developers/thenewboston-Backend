from django.contrib.auth.models import AbstractUser
from django.db import models

from thenewboston.wallets.models import Wallet

from ..managers.user import UserManager


class User(AbstractUser):
    avatar = models.ImageField(upload_to='images/', blank=True)
    manual_contribution_reward_daily_limit = models.PositiveBigIntegerField(default=0)
    # TODO(dmu) MEDIUM: If we have more permissions consider using Django built-in permission system
    is_manual_contribution_allowed = models.BooleanField(default=False)

    # `discord_user_id` and `discord_username` are implemented according to
    #  https://discord.com/developers/docs/resources/user
    discord_user_id = models.PositiveBigIntegerField(blank=True, null=True, unique=True)
    # `discord_username` is not used in logic and designed for representation purposes only (displaying to user)
    discord_username = models.CharField(max_length=32, blank=True, null=True)

    objects = UserManager()

    def get_reward_wallet_for_core(self, core_id, with_for_update=True):
        query = Wallet.objects
        if with_for_update:
            query = query.select_for_update()

        wallet, _ = query.get_or_create(core_id=core_id, owner=self)
        return wallet
