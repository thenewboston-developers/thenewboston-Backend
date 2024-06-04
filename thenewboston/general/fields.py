from rest_framework.fields import Field, empty
from rest_framework.serializers import ModelSerializer


class FixedField(Field):

    def __init__(self, serializer_class, *, default, serializer_kwargs=None, **kwargs):
        self._child_serializer_class = serializer_class
        self._child_serializer_kwargs = serializer_kwargs or {}
        super().__init__(default=default, **kwargs)

    def get_value(self, dictionary):
        # We always use the default value for `FixedField`.
        # User input is never provided or accepted.
        return empty

    def to_representation(self, value):
        kwargs = self._child_serializer_kwargs
        if issubclass(self._child_serializer_class, ModelSerializer):
            kwargs = kwargs | {'context': parent.context if (parent := getattr(self, 'parent', None)) else {}}

        return self._child_serializer_class(**kwargs).to_representation(value)

    def to_internal_value(self, data):
        return data
