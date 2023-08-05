from django.db import models

from thenewboston.general.models import CreatedModified


class Comment(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()

    def __str__(self):
        return self.content[:20]
