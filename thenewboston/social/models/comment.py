from django.db import models

from thenewboston.general.models import CreatedModified


class Comment(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    price_amount = models.PositiveBigIntegerField(blank=True, null=True)
    price_currency = models.ForeignKey('currencies.Currency', blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.content[:20]
