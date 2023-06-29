from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer

from thenewboston.general.serializers import ValidateFieldsMixin
from thenewboston.general.utils.cryptography import is_dict_signature_valid

from ..models.block import Block


class BlockSerializer(ValidateFieldsMixin, ModelSerializer):

    class Meta:
        model = Block
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)

        sender = attrs['sender']
        if sender == attrs['recipient']:
            raise ValidationError('Sender and recipient can not be the same')

        if not is_dict_signature_valid(attrs, attrs['sender'], attrs['signature']):
            raise ValidationError({'signature': ['Invalid']})

        return attrs

    @staticmethod
    def validate_transaction_fee(value):
        min_transaction_fee = 1

        if value < min_transaction_fee:
            raise ValidationError('Too small amount')

        return value
