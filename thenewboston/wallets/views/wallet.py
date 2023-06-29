from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.api.accounts import fetch_balance, transfer_funds
from thenewboston.general.constants import TRANSACTION_FEE
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.transfers.models import Transfer
from thenewboston.transfers.models.transfer import TransferType
from thenewboston.transfers.serializers.block import BlockSerializer
from thenewboston.transfers.serializers.transfer import TransferSerializer

from ..models import Wallet
from ..serializers.wallet import WalletReadSerializer, WalletWriteSerializer
from ..serializers.withdraw import WithdrawSerializer


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

        block = transfer_funds(
            amount=wallet.deposit_balance - TRANSACTION_FEE,
            domain=wallet.core.domain,
            recipient_account_number_str=settings.ACCOUNT_NUMBER,
            sender_signing_key_str=wallet.deposit_signing_key,
        )
        block_serializer = BlockSerializer(data=block)

        if block_serializer.is_valid(raise_exception=True):
            transfer = Transfer.objects.create(
                **block_serializer.validated_data,
                user=wallet.owner,
                core=wallet.core,
                transfer_type=TransferType.DEPOSIT,
            )
            wallet.balance += transfer.amount
            wallet.save()
        else:
            return Response({'error': 'Invalid block'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            deposit_balance = fetch_balance(account_number=wallet.deposit_account_number, domain=wallet.core.domain)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = deposit_balance
        wallet.save()

        response_data = {
            'transfer': TransferSerializer(transfer).data,
            'wallet': WalletReadSerializer(wallet, context={
                'request': request
            }).data,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def deposit_balance(self, request, pk=None):
        wallet = self.get_object()

        try:
            deposit_balance = fetch_balance(account_number=wallet.deposit_account_number, domain=wallet.core.domain)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = deposit_balance
        wallet.save()
        read_serializer = WalletReadSerializer(wallet, context={'request': request})

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

        block = transfer_funds(
            amount=amount - TRANSACTION_FEE,
            domain=wallet.core.domain,
            recipient_account_number_str=account_number,
            sender_signing_key_str=settings.SIGNING_KEY,
        )
        block_serializer = BlockSerializer(data=block)

        if block_serializer.is_valid(raise_exception=True):
            transfer = Transfer.objects.create(
                **block_serializer.validated_data,
                user=wallet.owner,
                core=wallet.core,
                transfer_type=TransferType.WITHDRAW,
            )
            wallet.balance -= amount
            wallet.save()
        else:
            return Response({'error': 'Invalid block'}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            'transfer': TransferSerializer(transfer).data,
            'wallet': WalletReadSerializer(wallet, context={
                'request': request
            }).data,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)
