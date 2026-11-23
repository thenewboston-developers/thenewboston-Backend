from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from thenewboston.currencies.models import Currency
from thenewboston.currencies.serializers.currency import CurrencyReadSerializer, CurrencyTinySerializer
from thenewboston.general.enums import NotificationType
from thenewboston.general.utils.text import truncate_text
from thenewboston.general.utils.transfers import transfer_coins
from thenewboston.notifications.models import Notification
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..constants import MAX_POST_IMAGES
from ..models import Post, PostLike
from ..serializers.comment import CommentReadSerializer
from ..serializers.post_image import PostImageReadSerializer
from ..utils.images import (
    get_images_for_post,
    get_post_image_thumbnail,
    remove_cover_image,
    replace_cover_image,
    set_post_images,
)
from ..utils.mentions import sync_mentioned_users


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    # The first of `images`, kept for clients that show one image per post
    image = serializers.ImageField(source='cover_image', read_only=True)
    images = PostImageReadSerializer(many=True, read_only=True)
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
            'images',
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
            'images',
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
            prefetched_likes = getattr(obj, '_prefetched_objects_cache', {}).get('likes')
            if prefetched_likes is not None:
                return any(like.user_id == request.user.id for like in prefetched_likes)
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False

    def get_tip_amounts(self, obj):
        prefetched_comments = getattr(obj, '_prefetched_objects_cache', {}).get('comments')
        if prefetched_comments is not None:
            totals = {}
            currencies = {}
            for comment in prefetched_comments:
                if comment.price_amount is None or comment.price_currency_id is None:
                    continue
                currency_id = comment.price_currency_id
                totals[currency_id] = totals.get(currency_id, 0) + comment.price_amount
                currencies[currency_id] = comment.price_currency
            return [
                {
                    'currency': CurrencyReadSerializer(currencies[currency_id], context=self.context).data,
                    'total_amount': total_amount,
                }
                for currency_id, total_amount in totals.items()
            ]

        tip_amounts = []
        comments_with_tips = obj.comments.filter(price_amount__isnull=False, price_currency__isnull=False)
        currency_sums = comments_with_tips.values('price_currency').annotate(total_amount=Sum('price_amount'))
        currency_ids = [item['price_currency'] for item in currency_sums]

        if currency_ids:
            currencies = {
                c.id: c
                for c in Currency.objects.filter(id__in=currency_ids).select_related('owner__connect_five_stats')
            }

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
    """
    The images of a post are set with `image_ids`: the ids of images uploaded through `/api/post-images`, in the
    order they are shown. On update the list replaces the images of the post, so it also names the images to keep.

    `image` (one file) and `clear_image` are the single-image API that preceded `image_ids`. They are still accepted
    and apply to the first image of the post.
    """

    clear_image = serializers.BooleanField(write_only=True, required=False)
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    image_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_empty=True, max_length=MAX_POST_IMAGES
    )
    mentioned_user_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_empty=True
    )

    class Meta:
        model = Post
        fields = (
            'content',
            'image',
            'image_ids',
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
        image = validated_data.pop('image', None)
        image_ids = validated_data.pop('image_ids', [])
        recipient = validated_data.get('recipient')
        price_amount = validated_data.get('price_amount')
        price_currency = validated_data.get('price_currency')
        # Checked before any coins move
        images = get_images_for_post(image_ids=image_ids, user=request.user)

        if price_amount is not None and price_currency is not None and recipient is not None:
            sender_wallet = Wallet.objects.select_for_update().get(owner=request.user, currency=price_currency)

            if sender_wallet.balance < price_amount:
                raise serializers.ValidationError('Insufficient funds')

            recipient_wallet, _ = Wallet.objects.select_for_update().get_or_create(
                owner=recipient, currency=price_currency, defaults={'balance': 0}
            )

            transfer_coins(sender_wallet=sender_wallet, recipient_wallet=recipient_wallet, amount=price_amount)

        post = super().create({**validated_data, 'owner': request.user})

        if images:
            set_post_images(post=post, images=images)
        elif image:
            replace_cover_image(post=post, image_file=image)

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
                'post_image_thumbnail': get_post_image_thumbnail(post, request),
                'post_created': post.created_date.isoformat(),
            },
        ).save(should_stream=True)

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Update the Post instance.

        This method updates the content and images of a Post instance.
        - If 'image_ids' is provided, the images of the post become exactly those images, in that order
        - If neither 'image_ids' nor the single-image fields are in the request, no changes are made to the images

        Single-image fields, which apply to the first image of the post:
        - If 'clear_image' is True, or None/null is provided for 'image', the image is removed
        - If a new 'image' is provided, it replaces the image

        Note: Transfer-related fields (recipient, price_amount, price_currency) cannot be updated.
        """
        validated_data.pop('recipient', None)
        validated_data.pop('price_amount', None)
        validated_data.pop('price_currency', None)
        mentioned_user_ids = validated_data.pop('mentioned_user_ids', serializers.empty)
        clear_image = validated_data.pop('clear_image', False)
        image = validated_data.pop('image', serializers.empty)
        image_ids = validated_data.pop('image_ids', serializers.empty)

        content = validated_data.get('content')

        if content is not None:
            instance.content = content

        instance.save()

        if image_ids is not serializers.empty:
            user = self.context['request'].user
            set_post_images(post=instance, images=get_images_for_post(image_ids=image_ids, user=user, post=instance))
        elif clear_image or image is None:
            remove_cover_image(post=instance)
        elif image is not serializers.empty:
            replace_cover_image(post=instance, image_file=image)

        if mentioned_user_ids is serializers.empty:
            if 'content' not in validated_data:
                return instance
            mention_ids = None
        else:
            mention_ids = mentioned_user_ids

        sync_mentioned_users(instance=instance, content=instance.content, mentioned_user_ids=mention_ids)
        return instance

    def validate(self, data):
        if 'image_ids' in data and ('image' in data or data.get('clear_image')):
            raise serializers.ValidationError('Use either image_ids or the single-image fields, not both.')

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
