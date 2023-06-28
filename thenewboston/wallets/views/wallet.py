from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.api.accounts import fetch_balance
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Wallet
from ..serializers.wallet import WalletReadSerializer, WalletWriteSerializer


class WalletViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Wallet.objects.none()

    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        wallet = self.get_object()

        try:
            balance = fetch_balance(account_number=wallet.deposit_account_number, domain=wallet.core.domain)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        wallet.deposit_balance = balance
        wallet.save()
        read_serializer = WalletReadSerializer(wallet, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        wallet = serializer.save()
        read_serializer = WalletReadSerializer(wallet, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        user = self.request.user
        return Wallet.objects.filter(owner=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return WalletWriteSerializer

        return WalletReadSerializer
