from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Whitepaper


class WhitepaperReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Whitepaper
        fields = '__all__'


class WhitepaperWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Whitepaper
        fields = ('currency', 'content')

    def create(self, validated_data):
        request = self.context.get('request')
        currency = validated_data['currency']

        if currency.owner != request.user:
            raise serializers.ValidationError('You must be the currency owner to create a whitepaper.')

        return super().create({
            **validated_data,
            'owner': request.user,
        })

    def update(self, instance, validated_data):
        request = self.context.get('request')

        if instance.owner != request.user:
            raise serializers.ValidationError('You must be the whitepaper owner to update it.')

        if 'currency' in validated_data and validated_data['currency'] != instance.currency:
            raise serializers.ValidationError('Currency cannot be changed.')

        return super().update(instance, validated_data)
