from django.db import transaction
from rest_framework import serializers

from thenewboston.general.utils.image import process_image
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Post
from ..serializers.comment import CommentReadSerializer


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    owner = UserReadSerializer(read_only=True)
    recipient = UserReadSerializer(read_only=True)

    class Meta:
        model = Post
        fields = (
            'comments', 'content', 'created_date', 'id', 'image', 'modified_date', 'owner', 'price_amount',
            'price_currency', 'recipient'
        )
        read_only_fields = (
            'comments',
            'content',
            'created_date',
            'id',
            'image',
            'modified_date',
            'owner',
            'price_amount',
            'price_currency',
            'recipient',
        )


class PostWriteSerializer(serializers.ModelSerializer):
    clear_image = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Post
        fields = ('content', 'image', 'recipient', 'price_amount', 'price_currency', 'clear_image')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        validated_data.pop('clear_image', None)  # Remove clear_image if present (only for updates)
        image = validated_data.get('image')
        recipient = validated_data.get('recipient')
        price_amount = validated_data.get('price_amount')
        price_currency = validated_data.get('price_currency')

        if image:
            file = process_image(image)
            validated_data['image'] = file

        if price_amount is not None and price_currency is not None and recipient is not None:
            sender_wallet = Wallet.objects.select_for_update().get(owner=request.user, currency=price_currency)

            if sender_wallet.balance < price_amount:
                raise serializers.ValidationError('Insufficient funds')

            recipient_wallet, _ = Wallet.objects.select_for_update().get_or_create(
                owner=recipient, currency=price_currency, defaults={'balance': 0}
            )

            transfer_coins(
                sender_wallet=sender_wallet,
                recipient_wallet=recipient_wallet,
                amount=price_amount,
                request=request,
            )

        post = super().create({
            **validated_data,
            'owner': request.user,
        })
        return post

    def update(self, instance, validated_data):
        """
        Update the Post instance.

        This method updates the content and image of a Post instance.
        - If 'clear_image' is True, the image is removed
        - If 'image' is not in the request, no changes are made to the image
        - If a new image is provided, it replaces the existing image
        - If None/null is provided for image, it clears the image

        Note: Transfer-related fields (recipient, price_amount, price_currency) cannot be updated.
        """
        validated_data.pop('recipient', None)
        validated_data.pop('price_amount', None)
        validated_data.pop('price_currency', None)
        clear_image = validated_data.pop('clear_image', False)

        instance.content = validated_data.get('content', instance.content)

        if clear_image:
            instance.image = None
        elif 'image' in validated_data:
            image = validated_data.get('image')

            if image is None:
                instance.image = None
            else:
                file = process_image(image)
                instance.image = file

        instance.save()
        return instance

    def validate(self, data):
        # Only validate transfer fields on create
        if not self.instance:
            user = self.context['request'].user
            recipient = data.get('recipient')
            price_amount = data.get('price_amount')
            price_currency = data.get('price_currency')

            fields_provided = [recipient is not None, price_amount is not None, price_currency is not None]
            if any(fields_provided) and not all(fields_provided):
                raise serializers.ValidationError(
                    'If any of recipient, price_amount, or price_currency is provided, all three must be provided.'
                )

            if recipient and recipient == user:
                raise serializers.ValidationError('You cannot send coins to yourself.')

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
