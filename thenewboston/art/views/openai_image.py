import promptlayer
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

<<<<<<< HEAD
from thenewboston.general.clients.openai import OpenAIClient
from thenewboston.cores.utils.core import get_default_core
=======
>>>>>>> 5230d6d (fix: checking balance before image creation and charging after image creation)
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
        serializer = OpenAIImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        description = serializer.validated_data['description']
        quantity = serializer.validated_data['quantity']
        try:
            self.charge_image_creation_fee(request.user, quantity)
            response = OpenAIClient.get_instance().generate_image(
                prompt=description,
                quantity=quantity,
            )

            self.charge_image_creation_fee(request.user, quantity)
            return Response(response.dict(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def has_sufficient_balance_for_image_creation(wallet, quantity):
        """
        Checks if user has sufficient balance in their default wallet for image creation
        """
        total_image_creation_fee = OPENAI_IMAGE_CREATION_FEE * quantity
        if total_image_creation_fee > wallet.balance:
            raise Exception(
                f'Insufficient balance. Total artwork creation fee: {total_image_creation_fee}, '
                f'Wallet balance: {wallet.balance}'
            )
        return True

    @staticmethod
    def charge_image_creation_fee(wallet, quantity):
        """
        Charges the image creation fee by deducting the calculated amount
        from the user's default wallet balance.
        """
        total_image_creation_fee = OPENAI_IMAGE_CREATION_FEE * quantity
        wallet.balance -= total_image_creation_fee
        wallet.save()
        wallet_data = WalletReadSerializer(wallet).data
        WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)
