from django.db import models

from thenewboston.general.models import CreatedModified
from thenewboston.wallets.models import Wallet


class GitHubUser(CreatedModified):
    github_id = models.PositiveIntegerField(unique=True)

    # TODO(dmu) LOW: Consider removing excessive `github_` prefix in `github_username`
    github_username = models.CharField(max_length=40)
    reward_recipient = models.ForeignKey('users.User', blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'GitHub User'
        verbose_name_plural = 'GitHub Users'

    def __str__(self):
        return f'ID: {self.pk} | GitHub ID: {self.github_id} | GitHub Username: {self.github_username}'

    def get_reward_wallet_for_core(self, core_id, with_for_update=True):
        if not (reward_recipient := self.reward_recipient):
            return None

        query = Wallet.objects
        if with_for_update:
            query = query.select_for_update()

        wallet, _ = query.get_or_create(core_id=core_id, owner=reward_recipient)
        return wallet
