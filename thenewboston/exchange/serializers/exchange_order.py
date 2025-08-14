from rest_framework.serializers import CurrentUserDefault, HiddenField, ValidationError

from thenewboston.exchange.models.exchange_order import ExchangeOrderStatus
from thenewboston.general.serializers import BaseModelSerializer

from .asset_pair import AssetPairTinySerializer
from ..models import ExchangeOrder


class ExchangeOrderReadSerializer(BaseModelSerializer):
    asset_pair = AssetPairTinySerializer()

    class Meta:
        model = ExchangeOrder
        # TODO(dmu) LOW: `fields = '__all__'` maybe prone to accidental exposure of sensitive data (newly added fields)
        fields = '__all__'


class ExchangeOrderCreateSerializer(BaseModelSerializer):
    owner = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = ExchangeOrder
        fields = ('id', 'owner', 'asset_pair', 'side', 'quantity', 'price', 'status')
        # It safer to define writeable fields explicitly, so adding new fields to the model
        # does not accidentally expose them for writing.
        read_only_fields = tuple(set(fields) - {'asset_pair', 'side', 'quantity', 'price'})


class ExchangeOrderUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = ExchangeOrder
        fields = ('asset_pair', 'side', 'quantity', 'price', 'status')
        # TODO(dmu) LOW: Support update of other fields (need to update the logic of )
        read_only_fields = tuple(set(fields) - {'status'})

    @staticmethod
    def validate_status(value):
        # TODO(dmu) HIGH: Implement a true state machine, so only particular transitions are allowed
        #                 (see similar TODO on ExchangeOrder model)
        if value != ExchangeOrderStatus.CANCELLED.value:
            raise ValidationError('Transition is not allowed.')

        return value
