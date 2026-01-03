from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from thenewboston.currencies.models import Currency
from thenewboston.currencies.serializers.currency import CurrencyReadSerializer, CurrencyTinySerializer
from thenewboston.general.enums import NotificationType
from thenewboston.general.utils.image import process_image
from thenewboston.general.utils.text import truncate_text
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.notifications.models import Notification
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..models import Post, PostLike
from ..serializers.comment import CommentReadSerializer
from ..utils.mentions import sync_mentioned_users


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    owner = UserReadSerializer(read_only=True)
    recipient = UserReadSerializer(read_only=True)
    price_currency = CurrencyTinySerializer(read_only=True)
    mentioned_users = UserReadSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    tip_amounts = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            'comments',
            'content',
            'created_date',
            'id',
            'image',
            'mentioned_users',
            'modified_date',
            'owner',
            'price_amount',
            'price_currency',
            'recipient',
            'like_count',
            'is_liked',
            'tip_amounts',
        )
        read_only_fields = (
            'comments',
            'content',
            'created_date',
            'id',
            'image',
            'mentioned_users',
            'modified_date',
            'owner',
            'price_amount',
            'price_currency',
            'recipient',
            'like_count',
            'is_liked',
            'tip_amounts',
        )

    @staticmethod
    def get_like_count(obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False

    def get_tip_amounts(self, obj):
        tip_amounts = []
        comments_with_tips = obj.comments.filter(price_amount__isnull=False, price_currency__isnull=False)
        currency_sums = comments_with_tips.values('price_currency').annotate(total_amount=Sum('price_amount'))
        currency_ids = [item['price_currency'] for item in currency_sums]

        if currency_ids:
            currencies = {c.id: c for c in Currency.objects.filter(id__in=currency_ids)}

            for item in currency_sums:
                currency = currencies.get(item['price_currency'])

                if currency:
                    tip_amounts.append(
                        {
                            'currency': CurrencyReadSerializer(currency, context=self.context).data,
                            'total_amount': item['total_amount'],
                        }
                    )

        return tip_amounts


class PostWriteSerializer(serializers.ModelSerializer):
    clear_image = serializers.BooleanField(write_only=True, required=False)
    mentioned_user_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_empty=True
    )

    class Meta:
        model = Post
        fields = (
            'content',
            'image',
            'recipient',
            'price_amount',
            'price_currency',
            'clear_image',
            'mentioned_user_ids',
        )

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        validated_data.pop('clear_image', None)  # Remove clear_image if present (only for updates)
        raw_mentioned_user_ids = validated_data.pop('mentioned_user_ids', [])
        mentions_provided = 'mentioned_user_ids' in self.initial_data
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

            transfer_coins(sender_wallet=sender_wallet, recipient_wallet=recipient_wallet, amount=price_amount)

        post = super().create({**validated_data, 'owner': request.user})
        mention_ids = raw_mentioned_user_ids if mentions_provided else None
        sync_mentioned_users(instance=post, content=post.content, mentioned_user_ids=mention_ids)

        if price_amount is not None and price_currency is not None and recipient is not None:
            self.notify_coin_transfer(post=post, request=request)

        return post

    @staticmethod
    def notify_coin_transfer(post, request):
        Notification(
            owner=post.recipient,
            payload={
                'notification_type': NotificationType.POST_COIN_TRANSFER.value,
                'owner': UserReadSerializer(post.owner, context={'request': request}).data,
                'content': post.content,
                'post_id': post.id,
                'price_amount': post.price_amount,
                'price_currency_id': post.price_currency.id,
                'price_currency_ticker': post.price_currency.ticker,
                'post_preview': truncate_text(post.content),
                'post_image_thumbnail': request.build_absolute_uri(post.image.url) if post.image else None,
                'post_created': post.created_date.isoformat(),
            },
        ).save(should_stream=True)

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
        mentioned_user_ids = validated_data.pop('mentioned_user_ids', serializers.empty)
        clear_image = validated_data.pop('clear_image', False)

        content = validated_data.get('content')

        if content is not None:
            instance.content = content

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

        if mentioned_user_ids is serializers.empty:
            if 'content' not in validated_data:
                return instance
            mention_ids = None
        else:
            mention_ids = mentioned_user_ids

        sync_mentioned_users(instance=instance, content=instance.content, mentioned_user_ids=mention_ids)
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
