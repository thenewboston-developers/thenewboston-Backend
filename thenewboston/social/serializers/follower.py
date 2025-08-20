from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Follower


class FollowerReadSerializer(serializers.ModelSerializer):
    follower = UserReadSerializer(read_only=True)
    following = UserReadSerializer(read_only=True)
    self_following = serializers.SerializerMethodField()

    class Meta:
        model = Follower
        fields = ('created_date', 'follower', 'following', 'self_following', 'id', 'modified_date')
        read_only_fields = fields

    def get_self_following(self, obj):
        """
        Determines if the currently logged-in user is following the specified user.

        This method is used when fetching followers of a user to check if the logged-in user
        is following each follower or not.
        """
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return Follower.objects.filter(follower=request.user, following=obj.follower).exists()
        return False


class FollowerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follower
        fields = ('following',)

    def create(self, validated_data):
        request = self.context.get('request')
        follower = super().create(
            {
                **validated_data,
                'follower': request.user,
            }
        )
        return follower

    def validate(self, data):
        request = self.context.get('request')

        if request.user == data['following']:
            raise serializers.ValidationError('You cannot follow yourself.')

        if Follower.objects.filter(follower=request.user, following=data['following']).exists():
            raise serializers.ValidationError('This relationship already exists.')

        return data

    def validate_follower(self, value):
        request = self.context.get('request')

        if value != request.user:
            raise serializers.ValidationError('You can only be the follower.')

        return value
