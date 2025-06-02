from django.db import models

from thenewboston.general.models import CreatedModified


class PostLike(CreatedModified):
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('post', 'user')
        ordering = ['-created_date']

    def __str__(self):
        return f'{self.user.username} likes {self.post}'
