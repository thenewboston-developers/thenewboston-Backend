from django.db import transaction
from rest_framework import serializers

from thenewboston.general.utils.image import process_image
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.social.serializers.post_reaction import PostReactionsReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Post
from ..serializers.comment import CommentReadSerializer


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    owner = UserReadSerializer(read_only=True)
    recipient = UserReadSerializer(read_only=True)
    user_reaction = serializers.SerializerMethodField()
    user_reactions = PostReactionsReadSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = (
            'comments', 'content', 'created_date', 'id', 'image', 'modified_date', 'owner', 'price_amount',
            'price_currency', 'recipient', 'user_reaction', 'user_reactions'
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

    def get_user_reaction(self, obj):
        return getattr(obj, 'user_reaction', None)


class PostWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Post
        fields = ('content', 'image', 'recipient', 'price_amount', 'price_currency')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        image = validated_data.get('image')
        recipient = validated_data.get('recipient')
        price_amount = validated_data.get('price_amount')
        price_currency = validated_data.get('price_currency')

        if image:
            file = process_image(image)
            validated_data['image'] = file

        # Handle coin transfer if price fields are provided
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
            )

        post = super().create({
            **validated_data,
            'owner': request.user,
        })
        return post

    def validate(self, data):
        # Only validate transfer fields on create
        if not self.instance:
            user = self.context['request'].user
            recipient = data.get('recipient')
            price_amount = data.get('price_amount')
            price_currency = data.get('price_currency')

            # Check if all three fields are provided together or none
            fields_provided = [recipient is not None, price_amount is not None, price_currency is not None]
            if any(fields_provided) and not all(fields_provided):
                raise serializers.ValidationError(
                    'If any of recipient, price_amount, or price_currency is provided, all three must be provided.'
                )

            # Prevent users from sending coins to themselves
            if recipient and recipient == user:
                raise serializers.ValidationError('You cannot send coins to yourself.')

            # Check if user has a wallet for the specified currency
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

    def update(self, instance, validated_data):
        """
        Update the Post instance.

        This method updates the content and image of a Post instance.
        - If 'image' is not in the request, no changes are made to the image
        - If a new image is provided, it replaces the existing image
        - If None/null is provided for image, it clears the image

        Note: Transfer-related fields (recipient, price_amount, price_currency) cannot be updated.
        """
        # Remove transfer-related fields from validated_data to prevent updates
        validated_data.pop('recipient', None)
        validated_data.pop('price_amount', None)
        validated_data.pop('price_currency', None)

        # Update content if provided
        instance.content = validated_data.get('content', instance.content)

        # Handle image updates
        if 'image' in validated_data:
            image = validated_data.get('image')
            if image is None:
                # If None/null is provided, clear the image
                instance.image = None
            else:
                # If a new image is provided, process and update it
                file = process_image(image)
                instance.image = file
        # If 'image' key is not in validated_data, keep the existing image

        instance.save()
        return instance
