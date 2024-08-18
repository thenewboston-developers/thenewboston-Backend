from django.db import models

from thenewboston.general.models import CreatedModified


class PostReaction(CreatedModified):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE)

    reaction = models.CharField(max_length=10)

    def __str__(self):
        return f'{self.user}-{self.reaction}'
