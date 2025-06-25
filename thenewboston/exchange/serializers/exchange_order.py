from rest_framework.serializers import CurrentUserDefault, HiddenField, ModelSerializer

from ..models import ExchangeOrder


class ExchangeOrderReadSerializer(ModelSerializer):

    class Meta:
        model = ExchangeOrder
        # TODO(dmu) LOW: `fields = '__all__'` maybe prone to accidental exposure of sensitive data (newly added fields)
        fields = '__all__'


class ExchangeOrderCreateSerializer(ModelSerializer):
    owner = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = ExchangeOrder
        fields = ('primary_currency', 'secondary_currency', 'order_type', 'quantity', 'price', 'status')


class ExchangeOrderUpdateSerializer(ModelSerializer):

    class Meta:
        model = ExchangeOrder
        fields = ('primary_currency', 'secondary_currency', 'order_type', 'quantity', 'price', 'status')
        # TODO(dmu) LOW: Support update of other fields (need to update the logic of )
        read_only_fields = tuple(set(fields) - {'status'})
