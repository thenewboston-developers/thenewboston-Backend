from django.db import models

from thenewboston.general.constants import ACCOUNT_NUMBER_LENGTH, SIGNING_KEY_LENGTH
from thenewboston.general.validators import HexStringValidator


class DepositAccount(models.Model):
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, primary_key=True)
    account_number = models.CharField(
        max_length=ACCOUNT_NUMBER_LENGTH, validators=(HexStringValidator(ACCOUNT_NUMBER_LENGTH),)
    )
    signing_key = models.CharField(max_length=SIGNING_KEY_LENGTH, validators=(HexStringValidator(SIGNING_KEY_LENGTH),))

    def __str__(self):
        return str(self.pk)
