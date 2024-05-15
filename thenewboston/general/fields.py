from rest_framework.fields import Field, empty


class FixedField(Field):

    def __init__(self, serializer_class, *, default, serializer_kwargs=None, **kwargs):
        self.__serializer_class = serializer_class
        self.__serializer_kwargs = serializer_kwargs or {}
        super().__init__(default=default, **kwargs)

    def get_value(self, dictionary):
        # We always use the default value for `FixedField`.
        # User input is never provided or accepted.
        return empty

    def to_representation(self, value):
        return self.__serializer_class(**self.__serializer_kwargs).to_representation(value)

    def to_internal_value(self, data):
        return data
