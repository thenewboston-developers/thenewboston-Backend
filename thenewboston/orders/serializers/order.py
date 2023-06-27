from rest_framework import serializers

from thenewboston.wallets.models import Wallet

from ..models import AssetPair, Order
from ..models.order import FillStatus, OrderType


class OrderReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = '__all__'


class OrderWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = (
            'primary_currency',
            'secondary_currency',
            'order_type',
            'quantity',
            'price',
            'fill_status',
        )

    def create(self, validated_data):
        request = self.context.get('request')
        order = super().create({
            **validated_data,
            'fill_status': FillStatus.OPEN,
            'filled_amount': 0,
            'owner': request.user,
        })
        return order

    def update(self, instance, validated_data):
        instance.fill_status = validated_data.get('fill_status', instance.fill_status)
        instance.save()
        return instance

    def validate(self, data):
        if self.instance is None:
            order_type = data.get('order_type')
            primary_currency = data.get('primary_currency')
            secondary_currency = data.get('secondary_currency')
            fill_status = data.get('fill_status', FillStatus.OPEN)

            if order_type == OrderType.BUY:
                self.validate_buy_order(data)
            elif order_type == OrderType.SELL:
                self.validate_sell_order(data)
        else:
            primary_currency = self.instance.primary_currency
            secondary_currency = self.instance.secondary_currency
            fill_status = data.get('fill_status', self.instance.fill_status)

        if not AssetPair.objects.filter(
            primary_currency=primary_currency,
            secondary_currency=secondary_currency,
        ).exists():
            raise serializers.ValidationError(
                'Asset pair for the given primary and secondary currency does not exist.'
            )

        if fill_status == FillStatus.CANCELLED and (
            self.instance is None or self.instance.fill_status not in [FillStatus.OPEN, FillStatus.PARTIALLY_FILLED]
        ):
            raise serializers.ValidationError("Can only cancel an order if it's OPEN or PARTIALLY_FILLED.")

        return data

    def validate_buy_order(self, data):
        request = self.context.get('request')
        secondary_currency = data.get('secondary_currency')
        wallet = Wallet.objects.filter(owner=request.user, core=secondary_currency).first()

        if not wallet:
            raise serializers.ValidationError('Wallet does not exist.')

        quantity = data.get('quantity')
        price = data.get('price')
        total = quantity * price

        if total > wallet.balance:
            raise serializers.ValidationError(f'Total of {total} exceeds wallet balance of {wallet.balance}')

    def validate_sell_order(self, data):
        request = self.context.get('request')
        primary_currency = data.get('primary_currency')
        wallet = Wallet.objects.filter(owner=request.user, core=primary_currency).first()

        if not wallet:
            raise serializers.ValidationError('Wallet does not exist.')

        quantity = data.get('quantity')

        if quantity > wallet.balance:
            raise serializers.ValidationError(f'Quantity of {quantity} exceeds wallet balance of {wallet.balance}')
