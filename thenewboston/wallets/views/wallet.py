from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.api.accounts import fetch_balance, wire_funds
from thenewboston.general.constants import TRANSACTION_FEE
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Wallet, Wire
from ..models.wire import WireType
from ..serializers.block import BlockSerializer
from ..serializers.wallet import WalletReadSerializer, WalletWriteSerializer
from ..serializers.wire import WireSerializer
from ..serializers.withdraw import WithdrawSerializer
from ..utils.wallet import get_default_wallet


class WalletViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Wallet.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        wallet = serializer.save()
        read_serializer = WalletReadSerializer(wallet, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def deposit(self, request, pk=None):
        wallet = self.get_object()
        minimum_balance = TRANSACTION_FEE + 1

        if wallet.deposit_balance < minimum_balance:
            return Response({'error': f'Minimum balance of {minimum_balance} required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        block = wire_funds(
            amount=wallet.deposit_balance - TRANSACTION_FEE,
            domain=wallet.currency.domain,
            recipient_account_number_str=settings.ACCOUNT_NUMBER,
            sender_signing_key_str=wallet.deposit_signing_key,
        )
        block_serializer = BlockSerializer(data=block)

        if block_serializer.is_valid(raise_exception=True):
            wire = Wire.objects.create(
                **block_serializer.validated_data,
                currency=wallet.currency,
                owner=wallet.owner,
                wire_type=WireType.DEPOSIT,
            )
            wallet.balance += wire.amount
            wallet.save()
        else:
            return Response({'error': 'Invalid block'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            deposit_balance = fetch_balance(
                account_number=wallet.deposit_account_number, domain=wallet.currency.domain
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = deposit_balance
        wallet.save()

        response_data = {
            'wallet': WalletReadSerializer(wallet, context={
                'request': request
            }).data,
            'wire': WireSerializer(wire).data,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def deposit_balance(self, request, pk=None):
        wallet = self.get_object()

        try:
            deposit_balance = fetch_balance(
                account_number=wallet.deposit_account_number, domain=wallet.currency.domain
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = deposit_balance
        wallet.save()
        read_serializer = WalletReadSerializer(wallet, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='default')
    def default_wallet(self, request):
        user = request.user
        default_wallet = get_default_wallet(user)

        if not default_wallet:
            return Response({'error': 'Default wallet not found.'}, status=status.HTTP_404_NOT_FOUND)

        read_serializer = WalletReadSerializer(default_wallet, context={'request': request})
        return Response(read_serializer.data, status=status.HTTP_200_OK)

    def get_queryset(self):
        user = self.request.user
        return Wallet.objects.filter(owner=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return WalletWriteSerializer

        return WalletReadSerializer

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        wallet = self.get_object()
        serializer = WithdrawSerializer(data=request.data, context={'wallet': wallet})
        serializer.is_valid(raise_exception=True)

        account_number = serializer.validated_data['account_number']
        amount = serializer.validated_data['amount']

        block = wire_funds(
            amount=amount - TRANSACTION_FEE,
            domain=wallet.currency.domain,
            recipient_account_number_str=account_number,
            sender_signing_key_str=settings.SIGNING_KEY,
        )
        block_serializer = BlockSerializer(data=block)

        if block_serializer.is_valid(raise_exception=True):
            wire = Wire.objects.create(
                **block_serializer.validated_data,
                currency=wallet.currency,
                owner=wallet.owner,
                wire_type=WireType.WITHDRAW,
            )
            wallet.balance -= amount
            wallet.save()
        else:
            return Response({'error': 'Invalid block'}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            'wallet': WalletReadSerializer(wallet, context={
                'request': request
            }).data,
            'wire': WireSerializer(wire).data,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)
