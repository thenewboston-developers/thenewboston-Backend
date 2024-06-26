from django.db import IntegrityError
from rest_framework import serializers

from ..models import CartProduct
from ..models.product import ActivationStatus
from ..serializers.product import ProductReadSerializer


class CartProductReadSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer()

    class Meta:
        model = CartProduct
        fields = '__all__'


class CartProductWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = CartProduct
        fields = '__all__'
        read_only_fields = (
            'created_date',
            'modified_date',
            'buyer',
        )

    def create(self, validated_data):
        request = self.context.get('request')

        try:
            cart_product = super().create({
                **validated_data,
                'buyer': request.user,
            })
        except IntegrityError:
            raise serializers.ValidationError('This product is already in your cart.')

        return cart_product

    def validate(self, attrs):
        attrs = super().validate(attrs)
        product = attrs['product']
        product_seller = product.seller
        quantity = attrs['quantity']

        if product.activation_status != ActivationStatus.ACTIVE:
            raise serializers.ValidationError('Product must be active to be added to the cart.')

        if product.quantity < quantity:
            raise serializers.ValidationError(
                f'The quantity requested exceeds the available quantity. Only {product.quantity} unit(s) available.'
            )

        request = self.context.get('request')
        cart_products = CartProduct.objects.filter(buyer=request.user)

        if cart_products.exists():
            existing_sellers = {item.product.seller for item in cart_products}

            if product_seller not in existing_sellers:
                raise serializers.ValidationError('You cannot add products from different sellers to the cart.')

        return attrs

    def validate_product(self, product):
        request = self.context.get('request')

        if product.seller == request.user:
            raise serializers.ValidationError('You cannot add your own product to the cart.')

        return product

    @staticmethod
    def validate_quantity(value):
        if value <= 0:
            raise serializers.ValidationError('Quantity must be greater than 0.')

        return value
