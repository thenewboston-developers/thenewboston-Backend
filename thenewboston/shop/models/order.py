from django.db import models

from thenewboston.general.models import CreatedModified


class Order(CreatedModified):
    buyer = models.ForeignKey('users.User', related_name='bought_orders', on_delete=models.CASCADE)
    seller = models.ForeignKey('users.User', related_name='sold_orders', on_delete=models.CASCADE)
    address = models.ForeignKey('shop.Address', related_name='orders', on_delete=models.CASCADE)

    def __str__(self):
        return f'Order ID: {self.pk} | Buyer: {self.buyer.username} | Seller: {self.seller.username}'
