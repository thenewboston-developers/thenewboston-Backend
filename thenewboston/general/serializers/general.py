from django_restql.serializers import NestedModelSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import CurrentUserDefault, SkipField

from ..fields import FixedField


class ValidateUnknownFieldsMixin:

    def validate(self, attrs):
        """
        Make front-end developers life easier when they make a typo in an
        optional attribute name.
        """
        attrs = super().validate(attrs)

        # TODO(dmu) MEDIUM: Nested serializers do not have `initial_data` (why?).
        #                   Produce a fix instead of current workaround
        if not hasattr(self, 'initial_data'):
            return attrs

        if unknown_fields := set(self.initial_data).difference(self.fields):
            raise ValidationError(f'Unknown field(s): {", ".join(sorted(unknown_fields))}')

        return attrs


class ValidateReadonlyFieldsMixin:

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # TODO(dmu) HIGH: Nested serializers do not have `initial_data` (why?).
        #                 Produce a fix instead of current workaround
        if not hasattr(self, 'initial_data'):
            return attrs

        readonly_fields = {field_name for field_name, field in self.fields.items() if field.read_only
                           } | set(getattr(self.Meta, 'read_only_fields', ()))

        if readonly_fields := set(self.initial_data) & readonly_fields:
            raise ValidationError(f'Readonly field(s): {", ".join(sorted(readonly_fields))}')

        return attrs


class ValidateFixedFieldsMixin:

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # TODO(dmu) HIGH: Nested serializers do not have `initial_data` (why?).
        #                 Produce a fix instead of current workaround
        if not hasattr(self, 'initial_data'):
            return attrs

        fixed_fields = {field_name for field_name, field in self.fields.items() if isinstance(field, FixedField)}

        if fixed_fields := set(self.initial_data) & fixed_fields:
            raise ValidationError(f'Fixed field(s): {", ".join(sorted(fixed_fields))}')

        return attrs


class ValidateFieldsMixin(ValidateUnknownFieldsMixin, ValidateReadonlyFieldsMixin, ValidateFixedFieldsMixin):
    pass


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
