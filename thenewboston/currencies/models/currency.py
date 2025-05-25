from django.db import models

from thenewboston.general.models import CreatedModified


class Currency(CreatedModified):
    domain = models.CharField(max_length=255, unique=True)
    logo = models.ImageField(upload_to='images/', blank=True)
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    ticker = models.CharField(max_length=5, unique=True)

    def __str__(self):
        return self.domain
