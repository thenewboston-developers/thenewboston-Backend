from collections import defaultdict

from django.db import transaction
from rest_framework import serializers

from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

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

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        cart_products = validated_data.pop('cart_products')
        payment_dict = validated_data.pop('payment_dict')
        seller = validated_data['seller']

        order = Order.objects.create(buyer=request.user, **validated_data)
        self.handle_cart_products(cart_products, order)
        self.handle_payment(payment_dict, request, seller)

        return order

    @staticmethod
    def get_payment_dict(cart_products):
        payment_dict = defaultdict(int)

        for cart_product in cart_products:
            core_id = cart_product.product.price_core.id
            total_price = cart_product.product.price_amount * cart_product.quantity
            payment_dict[core_id] += total_price

        return payment_dict

    @staticmethod
    def handle_cart_products(cart_products, order):
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

    @staticmethod
    def handle_payment(payment_dict, request, seller):
        for core_id, total_price in payment_dict.items():
            buyer_wallet = Wallet.objects.select_for_update().get(owner=request.user, core_id=core_id)
            seller_wallet, _ = Wallet.objects.select_for_update().get_or_create(owner=seller, core_id=core_id)

            if buyer_wallet.balance < total_price:
                raise serializers.ValidationError('Insufficient funds')

            transfer_coins(
                sender_wallet=buyer_wallet,
                recipient_wallet=seller_wallet,
                amount=total_price,
            )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        cart_products = CartProduct.objects.filter(buyer=request.user)
        product_sellers = {item.product.seller for item in cart_products}

        if not cart_products:
            raise serializers.ValidationError('The cart must contain at least one product.')

        if len(product_sellers) > 1:
            raise serializers.ValidationError('All products in the cart must be from the same seller.')

        self.validate_cart_product_quantities(cart_products)
        payment_dict = self.get_payment_dict(cart_products)
        self.validate_wallets_and_funds(payment_dict, request.user)

        attrs['cart_products'] = cart_products
        attrs['payment_dict'] = payment_dict
        attrs['seller'] = product_sellers.pop()

        return attrs

    def validate_address(self, value):
        request = self.context.get('request')

        if value.owner != request.user:
            raise serializers.ValidationError('Address does not belong to the authenticated user')

        return value

    @staticmethod
    def validate_cart_product_quantities(cart_products):
        for cart_product in cart_products:
            product = cart_product.product

            if product.quantity < cart_product.quantity:
                raise serializers.ValidationError(
                    f'Not enough quantity for product {product.name}. '
                    f'Required: {cart_product.quantity}, Available: {product.quantity}'
                )

    @staticmethod
    def validate_wallets_and_funds(payment_dict, user):
        for core_id, total_price in payment_dict.items():
            try:
                wallet = Wallet.objects.get(owner=user, core_id=core_id)
            except Wallet.DoesNotExist:
                raise serializers.ValidationError(f'No wallet found for core ID {core_id} for the authenticated user.')

            if wallet.balance < total_price:
                raise serializers.ValidationError(
                    f'Insufficient funds in wallet for core ID {core_id}. '
                    f'Required: {total_price}, Available: {wallet.balance}'
                )
