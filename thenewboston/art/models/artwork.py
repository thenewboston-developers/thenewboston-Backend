from django.db import models

from thenewboston.general.models import CreatedModified


class Artwork(CreatedModified):
    creator = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='created_artworks')
    description = models.TextField()
    image = models.ImageField(upload_to='images/')
    name = models.CharField(max_length=200)
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='owned_artworks')
    price_amount = models.PositiveBigIntegerField(blank=True, null=True)
    price_core = models.ForeignKey('cores.Core', blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f'Artwork ID: {self.pk} | ' f'Name: {self.name} | ' f'Description: {self.description}'
