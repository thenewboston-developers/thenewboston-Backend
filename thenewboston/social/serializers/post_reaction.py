from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import PostReaction


class PostReactionsReadSerializer(serializers.ModelSerializer):
    user = UserReadSerializer(read_only=True)

    class Meta:
        model = PostReaction
        fields = ('reaction', 'user')
        read_only_fields = (
            'user',
            'reaction',
        )


class PostReactionCreateUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = PostReaction
        fields = ['post', 'reaction']

    def create(self, validated_data):
        post = validated_data.get('post')
        reaction = validated_data.get('reaction')
        user = self.context['request'].user

        post_reaction, _ = PostReaction.objects.update_or_create(user=user, post=post, defaults={'reaction': reaction})
        return post_reaction
