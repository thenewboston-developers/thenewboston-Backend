from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from thenewboston.general.enums import MessageType
from thenewboston.notifications.consumers.notification import NotificationConsumer
from thenewboston.notifications.models import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

from ..models import Artwork, ArtworkTransfer

User = get_user_model()


class ArtworkPurchaseSerializer(serializers.ModelSerializer):
    artwork = serializers.PrimaryKeyRelatedField(queryset=Artwork.objects.all(), required=True)

    class Meta:
        model = ArtworkTransfer
        fields = ('artwork',)

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        artwork = validated_data.get('artwork')

        buyer_wallet = Wallet.objects.select_for_update().get(owner=request.user, core=artwork.price_core)

        if buyer_wallet.balance < artwork.price_amount:
            raise serializers.ValidationError('Insufficient funds')

        seller_wallet, _ = Wallet.objects.select_for_update().get_or_create(
            owner=artwork.owner, core=artwork.price_core, defaults={'balance': 0}
        )

        buyer_wallet.balance -= artwork.price_amount
        seller_wallet.balance += artwork.price_amount
        buyer_wallet.save()
        seller_wallet.save()

        artwork_transfer = ArtworkTransfer.objects.create(
            previous_owner=artwork.owner,
            new_owner=request.user,
            artwork=artwork,
            price_amount=artwork.price_amount,
            price_core=artwork.price_core,
        )

        artwork.owner = request.user
        artwork.price_amount = None
        artwork.price_core = None
        artwork.save()

        buyer_wallet_data = WalletReadSerializer(buyer_wallet, context={'request': request}).data
        WalletConsumer.stream_wallet(
            message_type=MessageType.UPDATE_WALLET,
            wallet_data=buyer_wallet_data,
        )

        seller_wallet_data = WalletReadSerializer(seller_wallet, context={'request': request}).data
        WalletConsumer.stream_wallet(
            message_type=MessageType.UPDATE_WALLET,
            wallet_data=seller_wallet_data,
        )

        notification = Notification.objects.create(
            owner=artwork_transfer.previous_owner,
            payload={
                'artwork_id': artwork.id,
                'buyer': UserReadSerializer(artwork_transfer.new_owner, context={
                    'request': request
                }).data,
                'notification_type': 'ARTWORK_PURCHASE',
            }
        )
        notification_data = NotificationReadSerializer(notification).data
        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )

        return artwork_transfer

    def validate(self, data):
        user = self.context['request'].user
        artwork = data['artwork']

        try:
            Wallet.objects.get(owner=user, core=artwork.price_core)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError(
                f'No wallet found for {artwork.price_core.ticker} for the authenticated user.'
            )

        return data

    def validate_artwork(self, artwork):
        user = self.context['request'].user

        if artwork.owner == user:
            raise serializers.ValidationError('You cannot purchase your own artwork.')

        if not artwork.price_amount or artwork.price_core is None:
            raise serializers.ValidationError('The artwork must have a specified price and a core.')

        return artwork
