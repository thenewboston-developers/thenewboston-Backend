from django.db import models


class Wallet(models.Model):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    balance = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'core'], name='unique_owner_core')]

    def __str__(self):
        return str(self.pk)
