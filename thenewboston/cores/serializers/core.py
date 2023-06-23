from rest_framework import serializers

from ..models import Core


class CoreReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Core
        fields = '__all__'


class CoreWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Core
        fields = '__all__'
        read_only_fields = (
            'created_date',
            'modified_date',
            'owner',
        )

    def create(self, validated_data):
        request = self.context.get('request')
        core = super().create({
            **validated_data,
            'owner': request.user,
        })
        return core
