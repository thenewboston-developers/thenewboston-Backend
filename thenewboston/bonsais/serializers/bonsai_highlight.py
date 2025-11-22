from rest_framework import serializers

from ..models import BonsaiHighlight


class BonsaiHighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonsaiHighlight
        fields = ('id', 'text', 'order')
        extra_kwargs = {
            'id': {'read_only': True, 'required': False},
            'order': {'required': False},
        }
