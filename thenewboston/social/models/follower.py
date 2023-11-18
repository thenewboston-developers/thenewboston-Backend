from django.db import models

from thenewboston.general.models import CreatedModified


class Follower(CreatedModified):
    follower = models.ForeignKey('users.User', related_name='following', on_delete=models.CASCADE)
    following = models.ForeignKey('users.User', related_name='followers', on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['follower', 'following'], name='unique_follower_following')]

    def __str__(self):
        return f'{self.follower} follows {self.following}'
