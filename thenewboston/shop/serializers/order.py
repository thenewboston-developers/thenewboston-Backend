from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import CartProduct, Order, OrderProduct
from .address import AddressSerializer
from .order_product import OrderProductSerializer


class OrderReadSerializer(serializers.ModelSerializer):
    address = AddressSerializer(read_only=True)
    buyer = UserReadSerializer(read_only=True)
    order_products = OrderProductSerializer(many=True, read_only=True)
    seller = UserReadSerializer(read_only=True)

    class Meta:
        model = Order
        fields = '__all__'


class OrderWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = ('address',)
        read_only_fields = (
            'created_date',
            'modified_date',
            'buyer',
            'seller',
        )

    def create(self, validated_data):
        request = self.context.get('request')
        cart_products = CartProduct.objects.filter(buyer=request.user)

        product_sellers = {item.product.seller for item in cart_products}

        if len(product_sellers) > 1:
            raise serializers.ValidationError('All products in the cart must be from the same seller.')

        seller = product_sellers.pop()
        order = Order.objects.create(buyer=request.user, seller=seller, **validated_data)

        for cart_product in cart_products:
            product = cart_product.product
            quantity = cart_product.quantity

            OrderProduct.objects.create(
                description=product.description,
                image=product.image,
                name=product.name,
                order=order,
                price_amount=product.price_amount,
                price_core=product.price_core,
                product=product,
                quantity=quantity,
            )

            cart_product.delete()
            product.quantity -= quantity
            product.save()

        return order

    def validate_address(self, value):
        request = self.context.get('request')

        if value.owner != request.user:
            raise serializers.ValidationError('Address does not belong to the authenticated user')

        return value
