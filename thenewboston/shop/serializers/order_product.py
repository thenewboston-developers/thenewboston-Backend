from rest_framework import serializers

from ..models import OrderProduct
from .product import ProductReadSerializer


class OrderProductSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer()

    class Meta:
        model = OrderProduct
        fields = '__all__'
