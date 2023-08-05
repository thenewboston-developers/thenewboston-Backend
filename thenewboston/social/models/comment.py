from django.db import models

from thenewboston.general.models import CreatedModified


class Comment(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE)
    content = models.TextField()

    def __str__(self):
        return self.content[:50]
