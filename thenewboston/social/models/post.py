from django.db import models

from thenewboston.general.models import CreatedModified


class Post(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    content = models.TextField()
    image = models.ImageField(upload_to='images/', blank=True)
    recipient = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='received_posts', blank=True, null=True
    )
    price_amount = models.PositiveBigIntegerField(blank=True, null=True)
    price_currency = models.ForeignKey('currencies.Currency', blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.content[:50]
