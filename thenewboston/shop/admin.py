from django.contrib import admin

from .models import Address, CartProduct, Order, OrderProduct, Product

admin.site.register(Address)
admin.site.register(CartProduct)
admin.site.register(Order)
admin.site.register(OrderProduct)
admin.site.register(Product)
