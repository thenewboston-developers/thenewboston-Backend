from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

from ..consumers.exchange_order import ExchangeOrderConsumer
from ..models import ExchangeOrder
from ..models.exchange_order import FillStatus, OrderType
from ..order_matching.order_matching_engine import OrderMatchingEngine
from ..serializers.exchange_order import ExchangeOrderReadSerializer, ExchangeOrderWriteSerializer


class ExchangeOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = ExchangeOrder.objects.all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        self.update_wallet_balance(order)
        order_data = ExchangeOrderReadSerializer(order).data
        ExchangeOrderConsumer.stream_exchange_order(
            message_type=MessageType.CREATE_EXCHANGE_ORDER, order_data=order_data
        )
        read_serializer = ExchangeOrderReadSerializer(order)

        order_matching_engine = OrderMatchingEngine()
        order_matching_engine.process_new_order(order)

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return ExchangeOrderWriteSerializer

        return ExchangeOrderReadSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        old_fill_status = instance.fill_status
        order = serializer.save()
        order_data = ExchangeOrderReadSerializer(order).data
        ExchangeOrderConsumer.stream_exchange_order(
            message_type=MessageType.UPDATE_EXCHANGE_ORDER, order_data=order_data
        )
        read_serializer = ExchangeOrderReadSerializer(order)

        if old_fill_status in [
            FillStatus.OPEN, FillStatus.PARTIALLY_FILLED
        ] and instance.fill_status == FillStatus.CANCELLED:
            unfilled_quantity = instance.quantity - instance.filled_amount

            if instance.order_type == OrderType.BUY:
                refund_amount = unfilled_quantity * instance.price
                refund_currency = instance.secondary_currency
            else:
                refund_amount = unfilled_quantity
                refund_currency = instance.primary_currency

            wallet = Wallet.objects.get(owner=instance.owner, core=refund_currency)
            wallet.balance += refund_amount
            wallet.save()
            wallet_data = WalletReadSerializer(wallet).data
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)

        return Response(read_serializer.data)

    @staticmethod
    def update_wallet_balance(order):
        if order.order_type == OrderType.BUY:
            wallet = Wallet.objects.filter(owner=order.owner, core=order.secondary_currency).first()
            wallet.balance -= order.quantity * order.price
        else:
            wallet = Wallet.objects.filter(owner=order.owner, core=order.primary_currency).first()
            wallet.balance -= order.quantity

        wallet.save()
        wallet_data = WalletReadSerializer(wallet).data
        WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)
