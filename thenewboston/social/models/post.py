from django.db import models

from thenewboston.general.models import CreatedModified


class Post(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    content = models.TextField()
    image = models.ImageField(upload_to='images/', blank=True)

    def __str__(self):
        return self.content[:50]
