from django.db import transaction
from rest_framework import serializers

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.general.utils.image import process_image
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Post, PostLike
from ..serializers.comment import CommentReadSerializer


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    owner = UserReadSerializer(read_only=True)
    recipient = UserReadSerializer(read_only=True)
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            'comments', 'content', 'created_date', 'id', 'image', 'modified_date', 'owner', 'price_amount',
            'price_currency', 'recipient', 'like_count', 'is_liked'
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
            'like_count',
            'is_liked',
        )

    @staticmethod
    def get_like_count(obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False


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

        if price_amount is not None and price_currency is not None and recipient is not None:
            self.notify_coin_transfer(post=post, request=request)

        return post

    @staticmethod
    def notify_coin_transfer(post, request):
        notification = Notification.objects.create(
            owner=post.recipient,
            payload={
                'notification_type': NotificationType.POST_COIN_TRANSFER.value,
                'owner': UserReadSerializer(post.owner, context={
                    'request': request
                }).data,
                'content': post.content,
                'post_id': post.id,
                'price_amount': post.price_amount,
                'price_currency_id': post.price_currency.id,
                'price_currency_ticker': post.price_currency.ticker,
            }
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        apply_on_commit(
            lambda nd=notification_data: NotificationConsumer.
            stream_notification(message_type=MessageType.CREATE_NOTIFICATION, notification_data=nd)
        )

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
