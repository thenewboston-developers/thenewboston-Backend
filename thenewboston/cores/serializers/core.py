from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers

from ..models import Core

User = get_user_model()


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

        if not request.user.is_staff:
            raise exceptions.PermissionDenied('You do not have permission to create a Core.')

        core = super().create({
            **validated_data,
            'owner': request.user,
        })

        return core
