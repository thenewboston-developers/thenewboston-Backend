from django_restql.serializers import NestedModelSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import CurrentUserDefault, HiddenField, SkipField

from ..fields import FixedField


class ValidateFieldsMixin:

    def validate(self, attrs):
        """
        Make front-end developers life easier when they make a typo in an
        optional attribute name. And also allows better unittests
        """
        attrs = super().validate(attrs)

        # TODO(dmu) MEDIUM: Nested serializers do not have `initial_data` (why?).
        #                   Produce a fix instead of current workaround
        if not hasattr(self, 'initial_data'):
            return attrs

        initial_fields_set = set(self.initial_data)
        if unknown_fields := initial_fields_set - set(self.fields):
            raise ValidationError(f'Unknown field(s): {", ".join(sorted(unknown_fields))}')

        all_readonly_fields = {field_name for field_name, field in self.fields.items() if field.read_only
                               } | set(getattr(self.Meta, 'read_only_fields', ()))
        if readonly_fields := initial_fields_set & all_readonly_fields:
            raise ValidationError(f'Readonly field(s): {", ".join(sorted(readonly_fields))}')

        all_fixed_fields = {field_name for field_name, field in self.fields.items() if isinstance(field, FixedField)}
        if fixed_fields := initial_fields_set & all_fixed_fields:
            raise ValidationError(f'Fixed field(s): {", ".join(sorted(fixed_fields))}')

        all_hidden_fields = {field_name for field_name, field in self.fields.items() if isinstance(field, HiddenField)}
        if hidden_fields := initial_fields_set & all_hidden_fields:
            raise ValidationError(f'Hidden field(s): {", ".join(sorted(hidden_fields))}')

        return attrs


class CreateOnlyCurrentUserDefault(CurrentUserDefault):

    def __call__(self, serializer_field):
        if serializer_field.parent.instance is not None:  # Parent instance exists: means it is an update
            raise SkipField()

        return super().__call__(serializer_field)


class BaseModelSerializer(ValidateFieldsMixin, NestedModelSerializer):
    # TODO(dmu) MEDIUM: Consider inheriting all serializers from this serializer
    def get_request(self):
        return self.context.get('request')

    def get_current_user(self):
        return self.get_request().user
