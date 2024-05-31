from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers
from rest_framework.fields import SkipField

from thenewboston.cores.utils.core import get_default_core

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
            # TODO(dmu) MEDIUM: Use `permission_classes` for checking permissions
            raise exceptions.PermissionDenied('You do not have permission to create a Core.')

        core = super().create({
            **validated_data,
            'owner': request.user,
        })

        return core


class CreateOnlyCoreDefault:
    """
    Default value class that returns a default core value only during creation,
    raises SkipField exception during updates.
    """

    def __init__(self):
        self.core = get_default_core()

    def set_context(self, serializer_field):
        pass

    def __call__(self, serializer_field=None):
        # Parent instance exists: means it is an update
        if serializer_field and serializer_field.parent.instance is not None:
            raise SkipField()

        return self.core

    def __repr__(self):
        return '%s()' % self.__class__.__name__
