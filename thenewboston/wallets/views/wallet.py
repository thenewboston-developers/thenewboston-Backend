from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.api.accounts import fetch_balance, transfer_funds
from thenewboston.blocks.serializers.block import BlockSerializer
from thenewboston.general.constants import TRANSACTION_FEE
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Wallet
from ..serializers.wallet import WalletReadSerializer, WalletWriteSerializer


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

        block_data = transfer_funds(
            amount=wallet.deposit_balance - TRANSACTION_FEE,
            domain=wallet.core.domain,
            recipient_account_number_str=settings.ACCOUNT_NUMBER,
            sender_signing_key_str=wallet.deposit_signing_key,
        )

        block_serializer = BlockSerializer(data=block_data)

        if block_serializer.is_valid():
            block = block_serializer.save()
            wallet.balance += block.amount
            wallet.save()

        try:
            deposit_balance = fetch_balance(account_number=wallet.deposit_account_number, domain=wallet.core.domain)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = deposit_balance
        wallet.save()
        wallet_serializer = WalletReadSerializer(wallet, context={'request': request})

        response_data = {
            'block': block_serializer.data,
            'wallet': wallet_serializer.data,
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
