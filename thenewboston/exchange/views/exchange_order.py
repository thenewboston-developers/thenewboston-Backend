from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType
from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

from ..consumers.asset_pair_exchange_order import AssetPairExchangeOrderConsumer
from ..models import ExchangeOrder
from ..models.exchange_order import ExchangeOrderType, FillStatus
from ..order_matching.order_matching_engine import OrderMatchingEngine
from ..serializers.exchange_order import ExchangeOrderReadSerializer, ExchangeOrderWriteSerializer


class ExchangeOrderViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = ExchangeOrder.objects.all()

    def get_queryset(self):
        return ExchangeOrder.objects.filter(owner=self.request.user).order_by('-created_date')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        self.update_wallet_balance(order, request)
        order_data = ExchangeOrderReadSerializer(order).data
        AssetPairExchangeOrderConsumer.stream_exchange_order(
            message_type=MessageType.CREATE_EXCHANGE_ORDER,
            order_data=order_data,
            primary_currency_id=order.primary_currency_id,
            secondary_currency_id=order.secondary_currency_id
        )
        read_serializer = ExchangeOrderReadSerializer(order)

        order_matching_engine = OrderMatchingEngine()
        order_matching_engine.process_new_order(order, request)

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
        AssetPairExchangeOrderConsumer.stream_exchange_order(
            message_type=MessageType.UPDATE_EXCHANGE_ORDER,
            order_data=order_data,
            primary_currency_id=order.primary_currency_id,
            secondary_currency_id=order.secondary_currency_id
        )
        read_serializer = ExchangeOrderReadSerializer(order)

        if old_fill_status in [
            FillStatus.OPEN, FillStatus.PARTIALLY_FILLED
        ] and instance.fill_status == FillStatus.CANCELLED:
            unfilled_quantity = instance.quantity - instance.filled_amount

            if instance.order_type == ExchangeOrderType.BUY:
                refund_amount = unfilled_quantity * instance.price
                refund_currency = instance.secondary_currency
            else:
                refund_amount = unfilled_quantity
                refund_currency = instance.primary_currency

            wallet = Wallet.objects.get(owner=instance.owner, currency=refund_currency)
            wallet.balance += refund_amount
            wallet.save()
            wallet_data = WalletReadSerializer(wallet, context={'request': request}).data
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)

        return Response(read_serializer.data)

    @staticmethod
    def update_wallet_balance(order, request):
        if order.order_type == ExchangeOrderType.BUY:
            wallet = Wallet.objects.filter(owner=order.owner, currency=order.secondary_currency).first()
            wallet.balance -= order.quantity * order.price
        else:
            wallet = Wallet.objects.filter(owner=order.owner, currency=order.primary_currency).first()
            wallet.balance -= order.quantity

        wallet.save()
        wallet_data = WalletReadSerializer(wallet, context={'request': request}).data
        WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)

    @action(detail=False, methods=['get'], url_path='book')
    def book(self, request):
        primary_currency_id = request.query_params.get('primary_currency')
        secondary_currency_id = request.query_params.get('secondary_currency')

        if not primary_currency_id or not secondary_currency_id:
            return Response({'error': 'Both primary_currency and secondary_currency parameters are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Get top 50 buy orders (highest price first)
        buy_orders = ExchangeOrder.objects.filter(
            primary_currency_id=primary_currency_id,
            secondary_currency_id=secondary_currency_id,
            order_type=ExchangeOrderType.BUY,
            fill_status__in=[FillStatus.OPEN, FillStatus.PARTIALLY_FILLED]
        ).order_by('-price')[:50]

        # Get top 50 sell orders (lowest price first)
        sell_orders = ExchangeOrder.objects.filter(
            primary_currency_id=primary_currency_id,
            secondary_currency_id=secondary_currency_id,
            order_type=ExchangeOrderType.SELL,
            fill_status__in=[FillStatus.OPEN, FillStatus.PARTIALLY_FILLED]
        ).order_by('price')[:50]

        buy_orders_data = ExchangeOrderReadSerializer(buy_orders, many=True).data
        sell_orders_data = ExchangeOrderReadSerializer(sell_orders, many=True).data

        return Response({'buy_orders': buy_orders_data, 'sell_orders': sell_orders_data})
