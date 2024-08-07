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


class OpenAIImageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request):
        try:
            serializer = OpenAIImageSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)

            description = serializer.validated_data['description']
            quantity = serializer.validated_data['quantity']

            response = OpenAIClient.get_instance().generate_image(prompt=description, quantity=quantity)

            self.charge_image_creation_fee(request.user, quantity)

            # TODO(dmu) LOW: Consider using status.HTTP_201_CREATED instead
            return Response(response.dict(), status=status.HTTP_200_OK)
        except Exception as e:
            # TODO(dmu) HIGH: This is invalid behavior to return HTTP400 in case of server side error.
            #                 It must be HTTP500. Exposing server side error details is not good due
            #                 security reasons. Also returning HTTP400 is confusing while debugging
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def charge_image_creation_fee(user, quantity):
        """
        Charges the image creation fee by deducting the calculated amount
        from the user's default wallet balance.
        """
        wallet = get_default_wallet(user)
        total_image_creation_fee = OPENAI_IMAGE_CREATION_FEE * quantity
        wallet.balance -= total_image_creation_fee
        wallet.save()
        wallet_data = WalletReadSerializer(wallet).data
        WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)
