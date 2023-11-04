from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from thenewboston.general.enums import MessageType
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

from ..models import Artwork, ArtworkTransfer

User = get_user_model()


class ArtworkPurchaseSerializer(serializers.ModelSerializer):
    artwork = serializers.PrimaryKeyRelatedField(queryset=Artwork.objects.all(), required=True)
    new_owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=True)

    class Meta:
        model = ArtworkTransfer
        fields = ('artwork', 'new_owner')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        artwork = validated_data.get('artwork')
        new_owner = validated_data.get('new_owner')

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
            new_owner=new_owner,
            artwork=artwork,
            price_amount=artwork.price_amount,
            price_core=artwork.price_core,
        )

        artwork.owner = new_owner
        artwork.save()

        buyer_wallet_data = WalletReadSerializer(buyer_wallet).data
        WalletConsumer.stream_wallet(
            message_type=MessageType.UPDATE_WALLET,
            wallet_data=buyer_wallet_data,
        )

        seller_wallet_data = WalletReadSerializer(seller_wallet).data
        WalletConsumer.stream_wallet(
            message_type=MessageType.UPDATE_WALLET,
            wallet_data=seller_wallet_data,
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

    def validate_new_owner(self, new_owner):
        user = self.context['request'].user

        if new_owner != user:
            raise serializers.ValidationError('You cannot purchase artwork for other users.')

        return new_owner
