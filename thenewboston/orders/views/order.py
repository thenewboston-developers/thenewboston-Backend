from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet

from ..consumers.order import OrderConsumer
from ..models import Order
from ..models.order import OrderType
from ..order_matching.order_matching_engine import OrderMatchingEngine
from ..serializers.order import OrderReadSerializer, OrderWriteSerializer


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Order.objects.all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        self.update_wallet_balance(order)
        OrderConsumer.stream_order(message_type=MessageType.CREATE_ORDER, order=order)
        read_serializer = OrderReadSerializer(order)

        order_matching_engine = OrderMatchingEngine()
        order_matching_engine.process_new_order(order)

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return OrderWriteSerializer

        return OrderReadSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        OrderConsumer.stream_order(message_type=MessageType.UPDATE_ORDER, order=order)
        read_serializer = OrderReadSerializer(order)

        return Response(read_serializer.data)

    @staticmethod
    def update_wallet_balance(order):
        if order.order_type == OrderType.BUY:
            wallet = Wallet.objects.filter(owner=order.owner, core=order.secondary_currency).first()
            total = order.quantity * order.price
            wallet.balance -= total
            wallet.save()
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet=wallet)
        elif order.order_type == OrderType.SELL:
            wallet = Wallet.objects.filter(owner=order.owner, core=order.primary_currency).first()
            wallet.balance -= order.quantity
            wallet.save()
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet=wallet)
