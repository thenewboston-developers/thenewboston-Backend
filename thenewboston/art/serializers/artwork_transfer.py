from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import ArtworkTransfer

User = get_user_model()


class ArtworkTransferReadSerializer(serializers.ModelSerializer):
    previous_owner = UserReadSerializer(read_only=True)
    new_owner = UserReadSerializer(read_only=True)

    class Meta:
        model = ArtworkTransfer
        fields = '__all__'


class ArtworkTransferWriteSerializer(serializers.ModelSerializer):
    new_owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=True)

    class Meta:
        model = ArtworkTransfer
        fields = ('artwork', 'new_owner')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        transfer = ArtworkTransfer.objects.create(
            **validated_data,
            previous_owner=request.user,
        )
        transfer.artwork.owner = transfer.new_owner
        transfer.artwork.price_amount = None
        transfer.artwork.price_core = None
        transfer.artwork.save()
        return transfer

    def validate(self, data):
        request = self.context.get('request')
        artwork = data['artwork']
        new_owner = data['new_owner']

        if artwork.owner != request.user:
            raise serializers.ValidationError('You do not own this artwork.')

        if new_owner == request.user:
            raise serializers.ValidationError('You cannot transfer artwork to yourself.')

        return data
