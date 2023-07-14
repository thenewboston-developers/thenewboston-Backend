from rest_framework import serializers

from ..models import OrderProduct


class OrderProductSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderProduct
        fields = '__all__'
