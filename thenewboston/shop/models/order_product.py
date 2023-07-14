from django.db import models

from .item import Item


class OrderProduct(Item):
    order = models.ForeignKey('shop.Order', related_name='order_products', on_delete=models.CASCADE)
    product = models.ForeignKey('shop.Product', related_name='order_products', on_delete=models.CASCADE)

    def __str__(self):
        return f'Order Product ID: {self.pk} | Order: {self.order.pk} | Product: {self.product.name}'
