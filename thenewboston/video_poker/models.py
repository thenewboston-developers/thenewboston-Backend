from django.db import models

from thenewboston.general.models import CreatedModified


class VideoPokerDraw(CreatedModified):
    """The one accepted draw of a hand. CasinoBet.result retains the verifiable action transcript."""

    bet = models.OneToOneField('casino.CasinoBet', on_delete=models.PROTECT)
    action_id = models.UUIDField()
    action = models.CharField(max_length=16)
