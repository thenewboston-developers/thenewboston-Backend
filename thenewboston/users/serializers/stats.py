from django.contrib.auth import get_user_model
from rest_framework import serializers

from thenewboston.wallets.utils.wallet import get_default_wallet

User = get_user_model()


class StatsSerializer(serializers.ModelSerializer):
    default_wallet_balance = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'default_wallet_balance', 'followers_count', 'following_count')

    @staticmethod
    def get_default_wallet_balance(obj):
        wallet = get_default_wallet(obj)
        return wallet.balance if wallet else 0

    @staticmethod
    def get_followers_count(obj):
        followers = getattr(obj, 'followers', None)
        return followers.count() if followers else 0

    @staticmethod
    def get_following_count(obj):
        following = getattr(obj, 'following', None)
        return following.count() if following else 0
