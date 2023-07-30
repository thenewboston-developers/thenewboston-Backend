from django.db import models


class InvitationLimit(models.Model):
    owner = models.OneToOneField('users.User', on_delete=models.CASCADE, related_name='invitation_limit')
    amount = models.PositiveIntegerField()

    def __str__(self):
        return f'{self.owner.username} | {self.amount}'
