import promptlayer
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.clients.openai import OpenAIClient
from thenewboston.general.constants import OPENAI_IMAGE_CREATION_FEE
from thenewboston.general.enums import MessageType
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.serializers.wallet import WalletReadSerializer
from thenewboston.wallets.utils.wallet import get_default_wallet

from ..serializers.openai_image import OpenAIImageSerializer

promptlayer.api_key = settings.PROMPTLAYER_API_KEY
OpenAI = promptlayer.openai.OpenAI


class OpenAIImageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request):
        try:
            serializer = OpenAIImageSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            description = serializer.validated_data['description']
            quantity = serializer.validated_data['quantity']
            total_image_creation_fee = OPENAI_IMAGE_CREATION_FEE * quantity

            wallet = get_default_wallet(request.user)
            if not wallet:
                raise Exception(f'Core {settings.DEFAULT_CORE_TICKER} wallet not found.')

            self.has_sufficient_balance_for_image_creation(wallet, total_image_creation_fee)

            response = OpenAIClient.get_instance().generate_image(
                prompt=description,
                quantity=quantity,
            )

            self.charge_image_creation_fee(wallet, total_image_creation_fee)

            # TODO(dmu) LOW: Consider using status.HTTP_201_CREATED instead
            return Response(response.dict(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def has_sufficient_balance_for_image_creation(wallet, total_image_creation_fee):
        """
        Checks if user has sufficient balance in their default wallet for image creation
        """
        if total_image_creation_fee > wallet.balance:
            raise Exception(
                f'Insufficient balance. Total artwork creation fee: {total_image_creation_fee}, '
                f'Wallet balance: {wallet.balance}'
            )

    @staticmethod
    def charge_image_creation_fee(wallet, total_image_creation_fee):
        """
        Charges the image creation fee by deducting the calculated amount
        from the user's default wallet balance.
        """
        wallet.balance -= total_image_creation_fee
        wallet.save()
        wallet_data = WalletReadSerializer(wallet).data
        WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)
