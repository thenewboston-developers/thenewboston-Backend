from collections import defaultdict

from django.db import transaction
from rest_framework import serializers

from thenewboston.general.enums import MessageType
from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

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
            core = cart_product.product.price_core
            total_price = cart_product.product.price_amount * cart_product.quantity
            payment_dict[core] += total_price

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
        key_pairs = {core.id: generate_key_pair() for core in payment_dict.keys()}

        for core, total_price in payment_dict.items():
            buyer_wallet = Wallet.objects.select_for_update().get(owner=request.user, core=core)
            seller_wallet, created = Wallet.objects.select_for_update().get_or_create(
                owner=seller,
                core=core,
                defaults={
                    'balance': 0,
                    'deposit_account_number': key_pairs[core.id].public,
                    'deposit_signing_key': key_pairs[core.id].private,
                }
            )

            if buyer_wallet.balance < total_price:
                raise serializers.ValidationError('Insufficient funds')

            buyer_wallet.balance -= total_price
            seller_wallet.balance += total_price

            buyer_wallet.save()
            seller_wallet.save()

            buyer_wallet_data = WalletReadSerializer(buyer_wallet).data
            WalletConsumer.stream_wallet(
                message_type=MessageType.UPDATE_WALLET,
                wallet_data=buyer_wallet_data,
            )

            seller_wallet_data = WalletReadSerializer(seller_wallet).data
            WalletConsumer.stream_wallet(
                message_type=MessageType.UPDATE_WALLET,
                wallet_data=seller_wallet_data,
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
        for core, total_price in payment_dict.items():
            try:
                wallet = Wallet.objects.get(owner=user, core=core)
            except Wallet.DoesNotExist:
                raise serializers.ValidationError(f'No wallet found for core {core} for the authenticated user.')

            if wallet.balance < total_price:
                raise serializers.ValidationError(
                    f'Insufficient funds in wallet for core {core}. '
                    f'Required: {total_price}, Available: {wallet.balance}'
                )
