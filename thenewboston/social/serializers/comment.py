from django.db import transaction
from rest_framework import serializers

from thenewboston.currencies.serializers.currency import CurrencyTinySerializer
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Comment
from ..utils.mentions import sync_mentioned_users


class CommentReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)
    price_currency = CurrencyTinySerializer(read_only=True)
    mentioned_users = UserReadSerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = (
            'content',
            'created_date',
            'id',
            'mentioned_users',
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
            'mentioned_users',
            'modified_date',
            'owner',
            'post',
            'price_amount',
            'price_currency',
        )


class CommentUpdateSerializer(serializers.ModelSerializer):
    mentioned_user_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_empty=True
    )

    class Meta:
        model = Comment
        fields = ('content', 'mentioned_user_ids')

    def update(self, instance, validated_data):
        mentioned_user_ids = validated_data.pop('mentioned_user_ids', serializers.empty)
        content = validated_data.get('content', instance.content)

        if 'content' in validated_data:
            instance.content = content
            instance.save(update_fields=['content'])

        if mentioned_user_ids is serializers.empty:
            if 'content' not in validated_data:
                return instance
            mention_ids = None
        else:
            mention_ids = mentioned_user_ids

        sync_mentioned_users(instance=instance, content=instance.content, mentioned_user_ids=mention_ids)

        return instance


class CommentWriteSerializer(serializers.ModelSerializer):
    mentioned_user_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_empty=True
    )

    class Meta:
        model = Comment
        fields = ('content', 'post', 'price_amount', 'price_currency', 'mentioned_user_ids')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        raw_mentioned_user_ids = validated_data.pop('mentioned_user_ids', [])
        mentions_provided = 'mentioned_user_ids' in self.initial_data
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

        comment = super().create({**validated_data, 'owner': request.user})
        mention_ids = raw_mentioned_user_ids if mentions_provided else None
        sync_mentioned_users(instance=comment, content=comment.content, mentioned_user_ids=mention_ids)

        return comment

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
