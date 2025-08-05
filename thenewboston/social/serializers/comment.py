from django.db import transaction
from rest_framework import serializers

from thenewboston.currencies.serializers.currency import CurrencyTinySerializer
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Comment


class CommentReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)
    price_currency = CurrencyTinySerializer(read_only=True)

    class Meta:
        model = Comment
        fields = (
            'content',
            'created_date',
            'id',
            'modified_date',
            'owner',
            'post',
            'price_amount',
            'price_currency',
        )
        read_only_fields = (
            'content',
            'created_date',
            'id',
            'modified_date',
            'owner',
            'post',
            'price_amount',
            'price_currency',
        )


class CommentUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Comment
        fields = ('content',)


class CommentWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Comment
        fields = ('content', 'post', 'price_amount', 'price_currency')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        post = validated_data.get('post')
        price_amount = validated_data.get('price_amount')
        price_currency = validated_data.get('price_currency')

        if price_amount is not None and price_currency is not None:
            commenter_wallet = Wallet.objects.select_for_update().get(owner=request.user, currency=price_currency)

            if commenter_wallet.balance < price_amount:
                raise serializers.ValidationError('Insufficient funds')

            poster_wallet, _ = Wallet.objects.select_for_update().get_or_create(
                owner=post.owner, currency=price_currency, defaults={'balance': 0}
            )

            transfer_coins(sender_wallet=commenter_wallet, recipient_wallet=poster_wallet, amount=price_amount)

        post = super().create({
            **validated_data,
            'owner': request.user,
        })

        return post

    def validate(self, data):
        user = self.context['request'].user
        price_amount = data.get('price_amount')
        price_currency = data.get('price_currency')

        if price_amount is not None and price_currency is None:
            raise serializers.ValidationError('If price_amount is given, price_currency must also be provided.')

        if price_currency is not None and price_amount is None:
            raise serializers.ValidationError('If price_currency is given, price_amount must also be provided.')

        if price_amount is not None and price_currency is not None:
            try:
                Wallet.objects.get(owner=user, currency=price_currency)
            except Wallet.DoesNotExist:
                raise serializers.ValidationError(
                    f'No wallet found for {price_currency.ticker} for the authenticated user.'
                )

        return data

    @staticmethod
    def validate_price_amount(value):
        if value is not None and value == 0:
            raise serializers.ValidationError('price_amount must be greater than 0.')

        return value
